# Packet Tracer Topology — Final Build Documentation
## Edge-Based ANPR & Speed Enforcement System

This document reflects the **actual, working configuration** as built and tested in Packet Tracer — it supersedes the original build guide, since several things changed during implementation (no WAN cloud/serial links were used, IP scheme was revised, and two real bugs were found and fixed during testing). Use this as the authoritative reference and as source material for your project report.

---

## Table of Contents

- [Final Topology](#final-topology)
- [Device List](#device-list)
- [IP Addressing Table](#ip-addressing-table)
- [VLAN Plan](#vlan-plan)
- [Final Router & Switch Configurations](#final-router--switch-configurations)
- [Mock CV/OCR Payload Demonstration](#mock-cvocr-payload-demonstration)
- [Testing & Validation Log](#testing--validation-log)
- [Report Writing Guide](#report-writing-guide)

---

## Final Topology

```
[Radar-Sensor] ─────────┐
                         ├──> [Edge-Router] ──> [Core-Router] ──> [Core-Switch]
[Edge-Node-PC] ──────────┘                                          │  │  │
                                                                     │  │  └── [Central-Server]  (VLAN 30)
                                                                     │  └───── [Officer-PC-1/2]   (VLAN 10)
                                                                     └──────── [Admin-PC]          (VLAN 20)
```

**Key change from the original plan:** the WAN-Cloud/serial-link design was dropped in favor of a direct copper Ethernet connection between Edge-Router and Core-Router, using each router's built-in Gigabit ports. This avoided needing WIC/serial modules and kept the build simpler without losing any of the security/segmentation logic being demonstrated.

---

## Device List

| Device | Model | Role |
|---|---|---|
| Radar-Sensor | PC-PT | Simulated radar/speed sensor |
| Edge-Node-PC | PC-PT | Simulated edge compute unit (CV/OCR host) |
| Edge-Router | Cisco 2911 | Roadside gateway |
| Core-Router | Cisco 1941 | Central gateway, VLAN routing (router-on-a-stick) |
| Core-Switch | Cisco 2960-24TT | LAN switch, VLAN + trunk |
| Central-Server | Server-PT | Hosts police portal (HTTP/HTTPS) |
| Officer-PC-1, Officer-PC-2 | PC-PT | Police VLAN clients |
| Admin-PC | PC-PT | Admin VLAN client |

---

## IP Addressing Table

| Device | Interface | IP Address | Subnet Mask | Gateway |
|---|---|---|---|---|
| Radar-Sensor | Fa0 | 172.16.1.2 | 255.255.255.0 | 172.16.1.1 |
| Edge-Router | Gig0/0 | 172.16.1.1 | 255.255.255.0 | — |
| Edge-Node-PC | Fa0 | 172.16.2.2 | 255.255.255.0 | 172.16.2.1 |
| Edge-Router | Gig0/1 | 172.16.2.1 | 255.255.255.0 | — |
| Edge-Router | Gig0/2 | 10.0.0.1 | 255.255.255.252 | — |
| Core-Router | Gig0/0 | 10.0.0.2 | 255.255.255.252 | — |
| Core-Router | Gig0/1.10 (Police) | 192.168.10.1 | 255.255.255.0 | — |
| Core-Router | Gig0/1.20 (Admin) | 192.168.20.1 | 255.255.255.0 | — |
| Core-Router | Gig0/1.30 (Server) | 192.168.30.1 | 255.255.255.0 | — |
| Central-Server | Fa0 | 192.168.30.10 | 255.255.255.0 | 192.168.30.1 |
| Officer-PC-1 | Fa0 | 192.168.10.11 | 255.255.255.0 | 192.168.10.1 |
| Officer-PC-2 | Fa0 | 192.168.10.12 | 255.255.255.0 | 192.168.10.1 |
| Admin-PC | Fa0 | 192.168.20.11 | 255.255.255.0 | 192.168.20.1 |

> Note on subnetting: `172.16.x.x` is classfully a Class B range (default /16), but this design deliberately subnets it into smaller /24 segments (VLSM) to isolate the radar and edge-node segments — this is standard, correct practice under CIDR and doesn't need to match the legacy classful default.

---

## VLAN Plan

| VLAN ID | Name | Ports (Core-Switch) | Subnet |
|---|---|---|---|
| 10 | POLICE_VLAN | Fa0/3, Fa0/4 | 192.168.10.0/24 |
| 20 | ADMIN_VLAN | Fa0/5 | 192.168.20.0/24 |
| 30 | SERVER_VLAN | Fa0/2 | 192.168.30.0/24 |
| — | Trunk to Core-Router | Gig0/1 | carries VLANs 10, 20, 30 |

---

## Final Router & Switch Configurations

### Edge-Router

```
hostname Edge-Router

interface GigabitEthernet0/0
 ip address 172.16.1.1 255.255.255.0
 no shutdown

interface GigabitEthernet0/1
 ip address 172.16.2.1 255.255.255.0
 no shutdown

interface GigabitEthernet0/2
 ip address 10.0.0.1 255.255.255.252
 no shutdown

ip route 0.0.0.0 0.0.0.0 10.0.0.2

access-list 100 permit tcp 172.16.0.0 0.0.255.255 host 192.168.30.10 eq 8443
access-list 100 deny ip any any
interface GigabitEthernet0/2
 ip access-group 100 out
```

### Core-Router

```
hostname Core-Router

interface GigabitEthernet0/0
 ip address 10.0.0.2 255.255.255.252
 no shutdown

interface GigabitEthernet0/1
 no shutdown

interface GigabitEthernet0/1.10
 encapsulation dot1Q 10
 ip address 192.168.10.1 255.255.255.0

interface GigabitEthernet0/1.20
 encapsulation dot1Q 20
 ip address 192.168.20.1 255.255.255.0

interface GigabitEthernet0/1.30
 encapsulation dot1Q 30
 ip address 192.168.30.1 255.255.255.0

ip route 172.16.1.0 255.255.255.0 10.0.0.1
ip route 172.16.2.0 255.255.255.0 10.0.0.1

! Combined ACL for the server-facing interface.
! IMPORTANT: order matters — "established" and specific permits MUST come
! before the final deny, and the ACL must be built in one pass (IOS always
! appends new lines to the end of a named ACL — you cannot insert lines
! in the middle after the fact without recreating it).
ip access-list extended COMBINED_SERVER_IN
 permit tcp host 192.168.30.10 any established
 permit tcp 172.16.0.0 0.0.255.255 host 192.168.30.10 eq 8443
 permit tcp 192.168.10.0 0.0.0.255 host 192.168.30.10 eq 443
 permit tcp 192.168.20.0 0.0.0.255 host 192.168.30.10 eq 443
 deny ip any any

interface GigabitEthernet0/1.30
 ip access-group COMBINED_SERVER_IN in

! Police -> Admin segmentation. Applied INBOUND (not outbound) on the
! Police VLAN's own gateway sub-interface — outbound placement here
! was found to break ARP/local traffic resolution during testing.
access-list 130 deny ip 192.168.10.0 0.0.0.255 192.168.20.0 0.0.0.255
access-list 130 permit ip any any

interface GigabitEthernet0/1.10
 ip access-group 130 in
```

### Core-Switch

```
hostname Core-Switch

vlan 10
 name POLICE_VLAN
vlan 20
 name ADMIN_VLAN
vlan 30
 name SERVER_VLAN

interface GigabitEthernet0/1
 switchport mode trunk
 switchport trunk allowed vlan 10,20,30

interface FastEthernet0/2
 switchport mode access
 switchport access vlan 30

interface FastEthernet0/3
 switchport mode access
 switchport access vlan 10

interface FastEthernet0/4
 switchport mode access
 switchport access vlan 10

interface FastEthernet0/5
 switchport mode access
 switchport access vlan 20
```

---

## Mock CV/OCR Payload Demonstration

Since Packet Tracer can't run real YOLO/OCR models, this section simulates the "edge OCR extracts a violation and dispatches it to the central server" step from your workflow, using tools Packet Tracer actually has.

### Concept

The Edge-Node-PC represents the onboard compute unit that would normally run YOLOv8 + OCR. Instead of real inference, we **manually author a JSON payload** representing what that pipeline would have produced, and use Packet Tracer's built-in Text Editor and Web Browser/FTP tools to demonstrate the payload being created and sent toward the Central-Server — completing the "police confirms violation" storyline end-to-end within the simulation.

### Step 1: Author the mock payload on Edge-Node-PC

1. Click **Edge-Node-PC → Desktop tab → Text Editor**.
2. Paste the following mock JSON payload (this represents what the real YOLOv8 + PaddleOCR pipeline would output):

```json
{
  "violation_id": "VIO-2026-00042",
  "timestamp": "2026-07-31T14:32:10Z",
  "location_id": "GANTRY-04",
  "speed_detected": 98,
  "speed_limit": 80,
  "plate_text_ocr": "TN38AB1234",
  "confidence_score": 0.94,
  "context_image_hash": "a94a8fe5ccb19ba61c4c0873d391e9879",
  "plate_image_hash": "6f1ed002ab5595859014ebf0951522d9"
}
```
3. **Save** this file as `violation_payload.json` (File → Save in the Text Editor).

### Step 2: "Dispatch" the payload to the Central-Server

Since Packet Tracer's simulated servers don't run a custom REST API, the most realistic way to demonstrate dispatch **within the tool's limits** is via FTP upload, which is a real, working protocol in Packet Tracer:

1. Click **Central-Server → Services tab → FTP** → toggle **On**.
2. Create a user account for the edge node, e.g. username `edge_uploader`, password `EdgeUpload@123`, with **Write** permission enabled (check the box) so it can upload but not necessarily read/delete other files.
3. On **Edge-Node-PC → Desktop tab → Command Prompt**, connect to the server via FTP:
   ```
   ftp 192.168.30.10
   ```
4. When prompted, log in with the `edge_uploader` credentials you created.
5. Use `put` to upload the file (In Packet Tracer's simplified FTP client, you may need to first confirm the file exists in the PC's simulated file system via the Text Editor's save dialog; some versions support `put violation_payload.json` directly).
6. Once uploaded, verify it landed by checking **Central-Server → Services → HTTP → File Manager** or **FTP** file list — the JSON file should now appear alongside the server's other files.

### Step 3: Tie it back to the storyline

Narrate this in your report/demo as:
> "The edge compute node (Edge-Node-PC) runs the CV/OCR pipeline locally. Once a violation is detected, it packages the event into an encrypted JSON payload (shown here in plaintext for demonstration) and dispatches it to the central server via a secure channel (represented here by FTP with authentication; in production this would be MQTT/HTTPS over mTLS and a VPN tunnel). The payload then sits in the raw_violation_queue, pending review by an authorized police officer through the portal — who confirms or rejects the case, at which point it becomes part of the confirmed_violations dataset used for hotspot analytics."

This closes the loop from **detection → payload → dispatch → arrival at the server**, which is the piece Packet Tracer can meaningfully simulate; the actual portal UI (login, review, confirm/reject buttons) would need to be built outside Packet Tracer (e.g., as a simple Flask/Django app), since Packet Tracer's HTTP server only serves static HTML.

### Optional stretch: build a static mock portal page

If you want the demo to visually resemble the police portal:
1. Click **Central-Server → Services → HTTP → File Manager → New File**.
2. Name it `violations.html` and paste a simple HTML table styled to show the mock violation (plate, speed, location, timestamp, and Confirm/Reject buttons as plain HTML — they won't be functional without a backend, but they demonstrate the intended UI).
3. Access it from Officer-PC-1's browser at `https://192.168.30.10/violations.html` to complete the visual demonstration.

---

## Testing & Validation Log

This is a genuinely useful section for your report — it shows the network was **actually tested and debugged**, not just built and assumed to work. Real projects always hit issues like these; documenting them demonstrates a proper engineering process.

### Issue 1 — VLAN configuration silently failed to apply

**Symptom:** Server was unreachable; `show vlan brief` on Core-Switch showed all ports still in default VLAN 1, despite having "pasted" the VLAN config earlier.

**Root cause:** The switch CLI was still in **user EXEC mode** (`Switch>`) rather than privileged/config mode when the configuration block was pasted. Commands requiring privileged mode were silently rejected without visibly breaking the paste.

**Fix:** Re-entered `enable` → `configure terminal` → `hostname Core-Switch` one command at a time to confirm each prompt change, then re-applied the VLAN and port configuration. Verified with `show vlan brief` that all ports landed in their correct VLANs.

**Lesson:** Always confirm the CLI prompt (`>` vs `#` vs `(config)#`) before pasting multi-line configuration blocks — a paste into the wrong mode can fail invisibly.

### Issue 2 — Duplicate `ip access-group ... in` overwrote the first ACL

**Symptom:** `show ip interface GigabitEthernet0/1.30` showed only ACL 120 as the active inbound list; ACL 110 (meant to permit the edge node's ingestion traffic) had silently disappeared.

**Root cause:** Cisco IOS allows only **one inbound ACL per interface per protocol**. Applying `ip access-group 110 in` followed immediately by `ip access-group 120 in` caused the second command to silently overwrite the first, rather than stacking them.

**Fix:** Combined both rule sets into a single named ACL (`COMBINED_SERVER_IN`) applied once to the interface.

**Lesson:** Multiple `ip access-group ... in` statements on the same interface don't combine — consolidate all required rules into a single ACL.

### Issue 3 — ACL blocked the server's own reply traffic

**Symptom:** HTTPS requests from Officer-PC-1 to the server timed out in the browser, even though the network path, VLANs, and trunk were all confirmed correct.

**Root cause:** The inbound ACL on the server's interface only permitted traffic **destined to** the server; it had no rule allowing the server's **outbound replies** back to the client, so return traffic was silently dropped by the implicit `deny ip any any`.

**Fix:** Added `permit tcp host 192.168.30.10 any established` to the ACL, which allows return traffic for connections that were already initiated inbound, without opening the server up to originate arbitrary outbound connections.

**Lesson:** A stateless inbound ACL must explicitly account for return traffic (via `established`) or use reflexive/stateful rules — it's easy to permit the request and forget the reply.

### Issue 4 — New ACL line appended in the wrong order

**Symptom:** After adding the `established` rule, it still didn't work — traffic hit the implicit deny before ever reaching the new line.

**Root cause:** IOS always appends new lines to the **end** of a named access-list; there is no way to insert a line in the middle without sequence numbers or recreating the ACL. The `established` permit landed after `deny ip any any`, making it unreachable.

**Fix:** Deleted the ACL (`no ip access-list extended COMBINED_SERVER_IN`) and recreated it from scratch in the correct order (permits first, `deny` last), then re-verified with `show access-lists`.

**Lesson:** When precise rule order matters, either build the whole ACL in one pass in the correct order, or use explicit sequence numbers (`ip access-list extended NAME` then `5 permit ...`, `10 permit ...`) to control placement.

### Issue 5 — Outbound ACL on a VLAN gateway interface broke local traffic

**Symptom:** After adding ACL 130 (Police→Admin segmentation) outbound on the Police VLAN's own gateway sub-interface, even basic pings to the gateway itself failed with "Destination host unreachable" — despite every other check (VLAN assignment, trunk, IP config) being confirmed correct.

**Root cause:** Applying an ACL **outbound** on an interface that's also the default gateway for directly-connected hosts can interfere with local traffic handling (ARP resolution and locally-destined replies) in a way that isn't obvious from the ACL's rule content alone.

**Fix:** Re-applied the same ACL logic **inbound** on the same sub-interface instead (`ip access-group 130 in`), which filters traffic entering the router from that VLAN without disrupting the router's own local traffic handling. Verified gateway ping worked again, and that Police→Admin traffic was still correctly blocked.

**Lesson:** Prefer inbound ACLs on the interface facing the *source* of traffic you want to control, rather than outbound ACLs on interfaces that also serve as a default gateway.

### Final Verification Results

| Test | From | To | Expected | Result |
|---|---|---|---|---|
| Ping own gateway | Officer-PC-1 | 192.168.10.1 | Success | ✅ 4/4 received |
<img width="305" height="145" alt="image" src="https://github.com/user-attachments/assets/e66ded9e-f0d5-4cf1-a25c-891f70a1add9" />

| Ping cross-VLAN (Admin) | Officer-PC-1 | 192.168.20.11 | Blocked | ✅ 100% loss (ACL 130 working) |
<img width="305" height="120" alt="image" src="https://github.com/user-attachments/assets/4025bec6-de01-4502-a5ef-09b78128551d" />

| HTTPS to portal | Officer-PC-1 | 192.168.30.10 | Success | ✅ Page loaded |
<img width="709" height="514" alt="image" src="https://github.com/user-attachments/assets/bf68a5eb-fef0-4967-9fd0-03e5902d0a8d" />

| HTTPS to portal | Officer-PC-2 | 192.168.30.10 | Success | ✅ Page loaded |
<img width="696" height="493" alt="image" src="https://github.com/user-attachments/assets/342740fc-946f-42dd-aefb-5a548f6bc6af" />

| HTTPS to portal | Admin-PC | 192.168.30.10 | Success | ✅ Page loaded |
<img width="691" height="485" alt="image" src="https://github.com/user-attachments/assets/f93e8dd6-1394-4717-93d7-bfb40c0d21c4" />


---


## The Final Topology 
<img width="608" height="470" alt="image" src="https://github.com/user-attachments/assets/35cbe89b-51d6-4e07-877d-944030b94887" />

---

## The Final Simulation
<img src="https://github.com/user-attachments/assets/971f4998-6d8f-4f51-95c1-791d507dc89d" width="600" />

---

## Report Writing Guide


For your project report, this session gives you strong material for a **"Testing & Validation"** or **"Implementation Challenges"** section, which many project evaluations specifically look for (it shows engineering rigor, not just a finished diagram). Suggested structure:

1. **Screenshot the final topology** (Physical/Logical view showing all devices and green connection lights).
2. **Screenshot each `show` command output** referenced in the Testing & Validation Log above (`show vlan brief`, `show ip interface brief`, `show access-lists`, the ping results, and the successful browser loads) — these serve as your evidence of a working system.
3. **Write up Issues 1-5 above** as your "problems encountered and resolved" narrative — this is exactly the kind of content that distinguishes a report showing real engineering process from one that just shows a static diagram.
4. **Include the mock payload JSON and FTP dispatch** as your "simulated CV/OCR and secure dispatch" section, explicitly noting where real hardware/software (YOLOv8, OCR, mTLS, MQTT) would replace the simulation in an actual deployment.
5. **Reference back to the system design README** (data minimization, police-only access, DPDP alignment) to tie the network implementation back to the original requirements.
