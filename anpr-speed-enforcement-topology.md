# Packet Tracer Build Guide
## Edge-Based ANPR & Speed Enforcement System — Network Simulation

> **Note:** Packet Tracer `.pkt` files are a proprietary binary format that only the Packet Tracer application can create/save. This guide gives you everything needed to build the exact topology yourself: device list, IP addressing, VLANs, and copy-paste-ready CLI configs. Follow it top to bottom and you'll have a working `.pkt` file in ~20-30 minutes.

---

## 1. Device List (What to Drag Into Packet Tracer)

| # | Device | Packet Tracer Object | Represents |
|---|---|---|---|
| 1 | Edge-Node-PC | PC (or IoT "Thing" if using MQTT sim) | Roadside radar/camera compute unit |
| 2 | Radar-Sensor | Generic IoT Sensor (or a second PC) | Simulated Doppler radar |
| 3 | Edge-Router | Router (e.g., 2911) | Roadside gateway / simulated 4G-5G uplink |
| 4 | WAN-Cloud | Cloud-PT | Simulated cellular/internet WAN |
| 5 | Core-Router | Router (e.g., 2911) | Central traffic-authority gateway |
| 6 | Core-Switch | Switch (2960) | LAN switch at HQ, handles VLANs |
| 7 | Central-Server | Server-PT | Hosts ingestion API + police portal + DB |
| 8 | Officer-PC-1, Officer-PC-2 | PC | Police client machines (Police VLAN) |
| 9 | Admin-PC | PC | Admin/analytics access (Admin VLAN) |

---

## 2. Topology Diagram (Logical Layout)

```
[Radar-Sensor] --- [Edge-Node-PC] --- [Edge-Router] === (Serial/WAN Link) === [WAN-Cloud]
                                                                                    |
                                                                             [Core-Router]
                                                                                    |
                                                                             [Core-Switch]
                                                                              /    |     \
                                                                   [Central-Server] |   [Admin-PC]
                                                                        (VLAN 30)   |   (VLAN 20)
                                                                              [Officer-PC-1/2]
                                                                                (VLAN 10)
```

**Connections:**
- Radar-Sensor ↔ Edge-Node-PC : FastEthernet (or IoT custom cable)
- Edge-Node-PC ↔ Edge-Router : FastEthernet0/0
- Edge-Router ↔ WAN-Cloud : Serial0/0/0 (simulates cellular uplink)
- WAN-Cloud ↔ Core-Router : Serial0/0/0
- Core-Router ↔ Core-Switch : GigabitEthernet0/0 (trunk port)
- Core-Switch ↔ Central-Server : FastEthernet (access port, VLAN 30)
- Core-Switch ↔ Officer-PC-1/2 : FastEthernet (access ports, VLAN 10)
- Core-Switch ↔ Admin-PC : FastEthernet (access port, VLAN 20)

---

## 3. VLAN Plan

| VLAN ID | Name | Purpose | Subnet |
|---|---|---|---|
| 10 | POLICE_VLAN | Officer client PCs — portal access only | 192.168.10.0/24 |
| 20 | ADMIN_VLAN | Admin/analytics access | 192.168.20.0/24 |
| 30 | SERVER_VLAN | Central server (DB + API + portal host) | 192.168.30.0/24 |

---

## 4. IP Addressing Table

| Device | Interface | IP Address | Subnet Mask | Gateway |
|---|---|---|---|---|
| Radar-Sensor | Fa0 | 172.16.0.2 | 255.255.255.0 | 172.16.0.1 |
| Edge-Node-PC | Fa0 | 172.16.0.3 | 255.255.255.0 | 172.16.0.1 |
| Edge-Router | Fa0/0 | 172.16.0.1 | 255.255.255.0 | — |
| Edge-Router | S0/0/0 | 203.0.113.1 | 255.255.255.252 | — |
| Core-Router | S0/0/0 | 203.0.113.2 | 255.255.255.252 | — |
| Core-Router | G0/0 (trunk) | — | — | — |
| Core-Router | G0/0.10 (Police) | 192.168.10.1 | 255.255.255.0 | — |
| Core-Router | G0/0.20 (Admin) | 192.168.20.1 | 255.255.255.0 | — |
| Core-Router | G0/0.30 (Server) | 192.168.30.1 | 255.255.255.0 | — |
| Central-Server | NIC | 192.168.30.10 | 255.255.255.0 | 192.168.30.1 |
| Officer-PC-1 | NIC | 192.168.10.11 | 255.255.255.0 | 192.168.10.1 |
| Officer-PC-2 | NIC | 192.168.10.12 | 255.255.255.0 | 192.168.10.1 |
| Admin-PC | NIC | 192.168.20.11 | 255.255.255.0 | 192.168.20.1 |

> `203.0.113.0/30` is used as the simulated WAN link between Edge-Router and Core-Router through the Cloud object (in Packet Tracer, configure the Cloud-PT's serial link to pass traffic between these subnets, or connect the two routers directly via serial cable if your version of Packet Tracer doesn't support cloud-to-cloud configuration).

---

## 5. Edge-Router CLI Config (Roadside Gateway)

Paste into Edge-Router's CLI (enable mode):

```
enable
configure terminal
hostname Edge-Router

interface FastEthernet0/0
 ip address 172.16.0.1 255.255.255.0
 no shutdown
 exit

interface Serial0/0/0
 ip address 203.0.113.1 255.255.255.252
 clock rate 64000
 no shutdown
 exit

! Default route pointing toward the core network over the WAN
ip route 0.0.0.0 0.0.0.0 203.0.113.2

! Restrict this router to only forward traffic toward the ingestion API port (8443) on the server
access-list 100 permit tcp 172.16.0.0 0.0.0.255 host 192.168.30.10 eq 8443
access-list 100 deny ip any any
interface FastEthernet0/0
 ip access-group 100 in
 exit

end
write memory
```

---

## 6. Core-Router CLI Config (Central Gateway + Sub-Interfaces for VLANs)

```
enable
configure terminal
hostname Core-Router

interface Serial0/0/0
 ip address 203.0.113.2 255.255.255.252
 no shutdown
 exit

! Trunk interface toward Core-Switch, split into sub-interfaces per VLAN (router-on-a-stick)
interface GigabitEthernet0/0
 no shutdown
 exit

interface GigabitEthernet0/0.10
 encapsulation dot1Q 10
 ip address 192.168.10.1 255.255.255.0
 exit

interface GigabitEthernet0/0.20
 encapsulation dot1Q 20
 ip address 192.168.20.1 255.255.255.0
 exit

interface GigabitEthernet0/0.30
 encapsulation dot1Q 30
 ip address 192.168.30.1 255.255.255.0
 exit

! Route back to the edge node subnet over the WAN link
ip route 172.16.0.0 255.255.255.0 203.0.113.1

! === ACLs enforcing the access rules from the README ===

! ACL 110: Only the edge-node subnet may reach the server's ingestion port
access-list 110 permit tcp 172.16.0.0 0.0.0.255 host 192.168.30.10 eq 8443
access-list 110 deny tcp any host 192.168.30.10 eq 8443

! ACL 120: Only the Police VLAN and Admin VLAN may reach the portal's HTTPS port (443)
access-list 120 permit tcp 192.168.10.0 0.0.0.255 host 192.168.30.10 eq 443
access-list 120 permit tcp 192.168.20.0 0.0.0.255 host 192.168.30.10 eq 443
access-list 120 deny tcp any host 192.168.30.10 eq 443

! ACL 130: Deny Police VLAN from reaching Admin VLAN directly (segmentation)
access-list 130 deny ip 192.168.10.0 0.0.0.255 192.168.20.0 0.0.0.255
access-list 130 permit ip any any

! Apply ACLs to the relevant sub-interfaces
interface GigabitEthernet0/0.30
 ip access-group 110 in
 ip access-group 120 in
 exit

interface GigabitEthernet0/0.10
 ip access-group 130 out
 exit

end
write memory
```

---

## 7. Core-Switch Config (VLAN Assignment + Trunk)

```
enable
configure terminal
hostname Core-Switch

vlan 10
 name POLICE_VLAN
 exit
vlan 20
 name ADMIN_VLAN
 exit
vlan 30
 name SERVER_VLAN
 exit

! Trunk port toward Core-Router
interface GigabitEthernet0/1
 switchport mode trunk
 switchport trunk allowed vlan 10,20,30
 exit

! Access ports for Officer PCs
interface FastEthernet0/1
 switchport mode access
 switchport access vlan 10
 exit

interface FastEthernet0/2
 switchport mode access
 switchport access vlan 10
 exit

! Access port for Admin PC
interface FastEthernet0/3
 switchport mode access
 switchport access vlan 20
 exit

! Access port for Central Server
interface FastEthernet0/4
 switchport mode access
 switchport access vlan 30
 exit

end
write memory
```

---

## 8. End-Device IP Configuration (Desktop > IP Configuration tab in Packet Tracer)

| Device | IP Address | Subnet Mask | Default Gateway |
|---|---|---|---|
| Radar-Sensor | 172.16.0.2 | 255.255.255.0 | 172.16.0.1 |
| Edge-Node-PC | 172.16.0.3 | 255.255.255.0 | 172.16.0.1 |
| Officer-PC-1 | 192.168.10.11 | 255.255.255.0 | 192.168.10.1 |
| Officer-PC-2 | 192.168.10.12 | 255.255.255.0 | 192.168.10.1 |
| Admin-PC | 192.168.20.11 | 255.255.255.0 | 192.168.20.1 |
| Central-Server | 192.168.30.10 | 255.255.255.0 | 192.168.30.1 |

---

## 9. Central-Server Service Configuration (Config tab in Packet Tracer)

On the **Central-Server** object:

1. Go to **Config > HTTP** — turn **HTTP/HTTPS ON**. This represents the police portal.
2. Go to **Config > SERVICES > DHCP** — leave OFF (we're using static IPs for a controlled demo).
3. Optional: **Config > FTP** — turn ON if you want to demonstrate secure file transfer of evidence images; create a user account (e.g., `edge_uploader`) with limited permissions.
4. On the **Desktop > Web Browser** of Officer-PC-1/2 and Admin-PC, test access to `http://192.168.30.10` — this should succeed.
5. On the **Desktop > Web Browser** of Edge-Node-PC, test access to `http://192.168.30.10` on port 443 — this should be **blocked** by ACL 120 (only ingestion port 8443 is allowed from that subnet), proving the segmentation works.

---

## 10. Verification Checklist (What to Test in Simulation Mode)

Use Packet Tracer's **Simulation Mode** to send test PDUs (Add Simple PDU) and confirm:

- [ ] Officer-PC-1 → Central-Server (port 443/HTTP): **Success**
- [ ] Admin-PC → Central-Server (port 443/HTTP): **Success**
- [ ] Edge-Node-PC → Central-Server (port 443/HTTP): **Blocked** (edge node should only reach ingestion port 8443, not the portal)
- [ ] Edge-Node-PC → Central-Server (port 8443 simulated ingestion): **Success**
- [ ] Officer-PC-1 → Admin-PC (direct ping): **Blocked** (VLAN segmentation via ACL 130)
- [ ] Officer-PC-1 → Officer-PC-2 (same VLAN): **Success**
- [ ] `show vlan brief` on Core-Switch: confirms VLANs 10/20/30 with correct port assignments
- [ ] `show ip interface brief` on Core-Router: confirms sub-interfaces up/up with correct IPs
- [ ] `show access-lists` on Core-Router: confirms ACL 110/120/130 are active and matching hits

---

## 11. Notes on Simulating the CV/OCR + MQTT Layer

Packet Tracer cannot run YOLO/OCR models. To represent the "edge OCR & payload dispatch" step in your demo:

- Use the **Edge-Node-PC's Text Editor or a simple HTML page** (via its Desktop apps) to show a mock JSON payload, e.g.:
  ```json
  {
    "violation_id": "VIO-2026-00042",
    "timestamp": "2026-07-30T14:32:10Z",
    "location_id": "GANTRY-04",
    "speed_detected": 98,
    "speed_limit": 80,
    "plate_text_ocr": "TN38AB1234",
    "confidence_score": 0.94,
    "image_hash": "a94a8fe5ccb19ba61c4c0873d391e987982fbbd3"
  }
  ```
- Send this as a simulated HTTP POST or FTP upload from Edge-Node-PC to Central-Server in Simulation Mode — this represents your "encrypted payload dispatch" step for the demo/viva, even though real MQTT/TLS negotiation isn't fully renderable in Packet Tracer.
- If your Packet Tracer version supports **IoT + MQTT (via the "MQTT" server service and IoT "Things")**, you can additionally set the Radar-Sensor as an IoT Thing publishing to an MQTT topic (`traffic/violations`) on the Central-Server acting as broker — this more literally demonstrates the MQTT-over-WebSockets layer from your original architecture.
