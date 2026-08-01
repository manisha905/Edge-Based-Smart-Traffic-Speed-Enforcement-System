# Edge-Based ANPR, Speed Enforcement & Hit-and-Run Detection System

A privacy-compliant, event-driven roadside monitoring architecture combining a single roadside radar, trigger-based video capture, edge computing, secure networking, and a police-only verification portal that routes confirmed cases into separate overspeeding and hit-and-run evidence databases.

> **Simulation Note:** Physical hardware (radar, cameras, Jetson/RPi) is represented using **Cisco Packet Tracer** network simulation objects. Real-world computer vision (YOLOv8, OCR) is mocked/scripted for demonstration purposes, since Packet Tracer cannot execute actual ML inference.

---

## Table of Contents

- [Project Overview](#project-overview)
- [System Roles & Access Control](#system-roles--access-control)
- [System Architecture](#system-architecture)
- [Workflow](#workflow)
- [Database Schema](#database-schema)
- [Network Topology (Cisco Packet Tracer)](#network-topology-cisco-packet-tracer)
- [Security Design](#security-design)
- [Tech Stack](#tech-stack)
- [Compliance & Legal Considerations](#compliance--legal-considerations)
- [Analytics & Reporting](#analytics--reporting)
- [Project Structure](#project-structure)
- [Setup Instructions](#setup-instructions)
- [Roadmap](#roadmap)
- [Disclaimer](#disclaimer)

---

## Project Overview

This project simulates a **single roadside gantry unit** that serves two enforcement purposes at once: automated overspeeding detection, and hit-and-run evidence capture. A single radar continuously monitors traffic and watches for two distinct conditions — a vehicle exceeding the speed threshold, or a sudden abnormal deceleration/stop pattern consistent with a collision. Either condition triggers the same downstream pipeline: the camera (otherwise off) begins recording a **5-second high-resolution video**, the edge compute node extracts every visible license plate from that clip via ANPR, and the video plus plate images are dispatched securely to the **nearest connected police station**.

A **restricted, police-only web portal** allows authorized officials to review the video evidence and classify each case as **Overspeeding**, **Hit-and-Run**, or **Reject** (false trigger). Based on that classification, the video and plate images are filed into one of two separate evidence databases — kept apart because the two case types have different legal handling, retention needs, and downstream use (e-challan issuance vs. active investigation).

The system is designed around three core principles:

1. **Data Minimization** — the camera does not roll continuously; it activates only for 5 seconds per trigger, and nothing is stored unless a trigger condition is met.
2. **Restricted Access** — only authenticated, authorized police officials can access the verification portal or either evidence database. The public never interacts with the system directly.
3. **Evidentiary Integrity** — every captured video and plate image is hashed at the point of capture to preserve a tamper-proof chain of custody for legal use, including hit-and-run investigations where the footage may be the primary lead.

---

## System Roles & Access Control

| Role | Access Level | Capabilities |
|---|---|---|
| **Radar + Edge Node** (simulated) | No portal access | Detects overspeed or accident conditions, triggers the camera, runs ANPR on the resulting clip, and dispatches the payload; cannot read/query either database |
| **Police Official (Verifier)** | Authenticated login | Views pending events in the queue, watches the video, sees extracted plate images, classifies each case (Overspeeding / Hit-and-Run / Reject) |
| **Admin** | Authenticated login (elevated) | Manages officer accounts, configures gantry thresholds, views the combined analytics dashboard across both databases, audit logs |
| **Vehicle Owner / Public** | **No access** | Receives only the final e-challan notice (overspeeding cases only); never touches the system |

Access to the portal is restricted at both the **application layer** (login + Role-Based Access Control) and the **network layer** (VLAN segmentation + ACLs in Packet Tracer, so unauthorized subnets cannot even reach the portal's ports).

### What each simulated PC represents

| Device | Represents | Role |
|---|---|---|
| **Edge-Node-PC** | Roadside compute unit (Jetson/RPi in real deployment) | Runs the ANPR pipeline: receives the radar's trigger, controls the camera, processes the 5-second clip, extracts all visible plates, packages the payload, and dispatches it one-way to the police station server. Never authenticates into the portal — it only pushes data into the raw queue via the ingestion API. |
| **Officer-PC-1 / Officer-PC-2** | Individual police officers' workstations at the station | Where verification actually happens — an officer logs in, watches the video, reviews the extracted plate images, and classifies the case. Two exist to simulate multiple officers working the queue concurrently and to demonstrate that Police VLAN access isn't limited to a single device. |
| **Admin-PC** | Supervisor/admin workstation | Higher-privilege access: manages officer accounts, configures per-gantry thresholds, and is the only client with access to the **combined analytics dashboard** (accident hotspots + overspeeding hotspots pulled from both databases). |

---

## System Architecture

```
 ┌─────────────────────────┐
 │  Radar (single unit)      │  Continuous monitoring for TWO conditions:
 │                            │   1) Speed > threshold           → trigger_type: overspeed
 │                            │   2) Abnormal deceleration/stop  → trigger_type: accident
 └────────────┬───────────────┘
              │ Trigger condition met
              ▼
 ┌─────────────────────────┐
 │  Camera (idle by default)  │  Powers on ONLY on trigger
 │  Records 5-second HD video │  Returns to idle immediately after
 └────────────┬───────────────┘
              ▼
 ┌─────────────────────────┐
 │  Edge Compute Node          │  YOLOv8 + OpenCV + OCR (PaddleOCR/Tesseract)
 │  (Jetson/RPi - simulated)   │  Extracts ALL visible plates from the clip
 │                              │  SHA-256 hash of video + each plate image
 └────────────┬───────────────┘
              │ MQTT/HTTPS over mTLS + VPN tunnel
              ▼
 ┌─────────────────────────┐
 │  Nearest Police Station      │  Ingestion API → raw_event_queue
 │  Central Server               │
 └────────────┬───────────────┘
              ▼
 ┌─────────────────────────┐
 │  Police Portal                │  Login-restricted review interface
 │  (RBAC enforced)              │  Officer watches video + plate images
 └────────────┬───────────────┘
              │ Officer classifies case
              ▼
        ┌─────┴─────┐
        ▼           ▼
 ┌───────────┐ ┌───────────────┐
 │ confirmed_ │ │ confirmed_    │  → e-challan dispatch (overspeeding only)
 │ overspeeding│ │ hitandrun     │  → Feeds combined analytics dashboard
 └───────────┘ └───────────────┘
```

---

## Workflow

1. **Continuous Radar Monitoring** — A single radar scans approaching traffic and simultaneously watches for two conditions: speed exceeding the zone threshold, and abnormal deceleration/stop patterns consistent with a collision.
2. **Trigger Evaluation** — The edge computer evaluates each reading. Normal traffic is discarded from RAM instantly; no camera activity, no logging.
3. **Video Capture** — On either trigger type, the camera (otherwise off) activates and records a **5-second high-resolution video** of the scene, then returns to idle.
4. **Edge ANPR & Metadata Packaging** — YOLOv8 + OCR process the clip and extract **every visible license plate** (not just the triggering vehicle, since hit-and-run scenes may involve multiple vehicles). The video, cropped plate images, trigger type, speed data (if applicable), location ID, and timestamp are packaged into an encrypted payload with SHA-256 hashes for the video and each plate image.
5. **Secure Dispatch** — The payload is sent over MQTT/HTTPS via mTLS and a VPN tunnel to the **central server of the nearest connected police station** (routed by the gantry's `location_id`), landing in `raw_event_queue`.
6. **Police Verification** — An authorized officer logs into the portal, watches the video, reviews the extracted plate images, and classifies the case as **Overspeeding**, **Hit-and-Run**, or **Reject**.
7. **Classification & Filing** — Based on the officer's classification, the video and plate images move into either `confirmed_overspeeding` or `confirmed_hitandrun`. Overspeeding cases additionally trigger an e-challan notice (mocked); hit-and-run cases become active investigation leads, with the plate images serving as the primary means of identifying the vehicle/owner.
8. **Analytics** — Both confirmed databases feed a combined analytics dashboard, identifying zones with high overspeeding frequency separately from zones with high accident/hit-and-run frequency — since these may call for different enforcement responses (speed cameras vs. physical patrol or road-design review).

---

## Database Schema

Three tables: one shared intake queue, and two separate confirmed-evidence tables — kept apart because overspeeding and hit-and-run cases have different legal handling, retention rules, and downstream actions.

### `raw_event_queue` (pre-classification, shared intake)

| Field | Type | Description |
|---|---|---|
| `event_id` | UUID / PK | Unique event identifier |
| `trigger_type` | ENUM | `overspeed` / `accident` (as flagged by the radar/edge node) |
| `timestamp` | DATETIME | Time of detection |
| `location_id` | VARCHAR | Gantry/zone identifier |
| `speed_detected` | FLOAT (nullable) | Recorded speed, if overspeed trigger |
| `speed_limit` | FLOAT (nullable) | Zone threshold at time of event |
| `video_file_ref` | VARCHAR | Reference/path to the 5-second clip |
| `video_hash` | VARCHAR (SHA-256) | Hash of the video at capture time |
| `detected_plates` | JSON | Array of `{plate_text_ocr, confidence_score, image_hash}` for every plate found in the clip |
| `status` | ENUM | `pending` / `classified_overspeeding` / `classified_hitandrun` / `rejected` |

### `confirmed_overspeeding` (post-classification)

| Field | Type | Description |
|---|---|---|
| `event_id` | UUID / FK | References the raw queue entry |
| `officer_id` | VARCHAR | ID of confirming official |
| `confirmation_timestamp` | DATETIME | When the case was classified |
| `location_id` | VARCHAR | Gantry/zone identifier |
| `zone_coordinates` | GEO / VARCHAR | Lat-long or descriptive location |
| `speed_detected` | FLOAT | Confirmed recorded speed |
| `plate_text` | VARCHAR | Verified plate string of the offending vehicle |
| `video_file_ref` | VARCHAR | Retained evidence clip |
| `action_taken` | ENUM | `echallan_issued` / `warning` |

### `confirmed_hitandrun` (post-classification, active investigation evidence)

| Field | Type | Description |
|---|---|---|
| `event_id` | UUID / FK | References the raw queue entry |
| `officer_id` | VARCHAR | ID of confirming official |
| `confirmation_timestamp` | DATETIME | When the case was classified |
| `location_id` | VARCHAR | Gantry/zone identifier |
| `zone_coordinates` | GEO / VARCHAR | Lat-long or descriptive location |
| `video_file_ref` | VARCHAR | Retained evidence clip (primary exhibit) |
| `detected_plates` | JSON | All plates visible in the clip, as investigative leads |
| `case_status` | ENUM | `open` / `under_investigation` / `closed` |
| `investigating_officer_id` | VARCHAR | Assigned investigator, if different from the reviewing officer |

### `officer_accounts`

| Field | Type | Description |
|---|---|---|
| `officer_id` | VARCHAR / PK | Unique police ID |
| `password_hash` | VARCHAR | Bcrypt-hashed password |
| `role` | ENUM | `officer` / `admin` |
| `station_id` | VARCHAR | Assigned station/jurisdiction |
| `last_login` | DATETIME | Audit tracking |

---

## Network Topology (Cisco Packet Tracer)

Since physical hardware is simulated, the project focuses on **network design, segmentation, and access control**.

| Component | Packet Tracer Object | Purpose |
|---|---|---|
| Roadside Edge Node | PC | Represents Jetson/RPi edge compute |
| Radar (single unit) | PC | Simulated dual-purpose sensor (speed + anomaly detection) |
| Edge Gateway Router | Router | Roadside gateway toward the police station network |
| Central Server | Server (HTTP/DB services) | Hosts ingestion API + police portal, tagged to the nearest station's `location_id` |
| Police Client PCs | PCs on a dedicated VLAN | Access portal only |
| Firewall/ACL Enforcement | Router ACLs | Restrict traffic by subnet/port |

### Key Design Requirements

- **VLAN Segmentation**: Police client subnet, admin subnet, and server subnet are logically separated.
- **Access Control Lists (ACLs)**:
  - Edge node → allowed only to reach the server's ingestion API port.
  - Police subnet → allowed only to reach the portal's HTTPS port, and only for return traffic on established connections.
  - Police subnet → blocked from reaching the Admin subnet directly.
  - All other traffic → denied by default (deny-all fallback rule).
- **Simulated HTTPS**: Enable HTTP/HTTPS services on the Packet Tracer server object to demonstrate encrypted access to the portal.

---

## Security Design

| Layer | Mechanism |
|---|---|
| Device Authentication | Mutual TLS (mTLS) between edge node and server |
| Data Integrity | SHA-256 hashing of the video and each plate image at capture time (chain of custody) |
| Transport Security | HTTPS/MQTT over TLS; VPN tunnel over cellular uplink |
| Application Access | Login + Role-Based Access Control (Officer vs Admin) |
| Network Access | VLAN segmentation + router ACLs restricting subnet-to-port access |
| Session Management | Token-based sessions (JWT) with auto-timeout |
| Audit Trail | Logging of every classification action with officer ID and timestamp |

---

## Tech Stack

**Computer Vision (simulated/mocked in this phase)**
- OpenCV — video frame preprocessing
- YOLOv8/v10 — vehicle & plate detection across video frames
- PaddleOCR / Tesseract — plate text extraction (fine-tuned for Indian plate formats)

**Backend / Portal**
- Python (Flask/Django) or Node.js (Express)
- JWT-based authentication, bcrypt password hashing
- REST API for ingestion + portal endpoints
- Video streaming/playback support in the officer review UI

**Database**
- PostgreSQL / MySQL (relational, supports the three-table intake/classification split)

**Networking (Simulated)**
- Cisco Packet Tracer — topology, VLANs, ACLs, simulated VPN/HTTPS
- MQTT (Mosquitto) — lightweight edge telemetry
- HTTPS REST APIs — payload dispatch

**Frontend (Portal Dashboard)**
- HTML/CSS/JS or a lightweight framework (React) for the video review UI, classification controls, and analytics charts

---

## Compliance & Legal Considerations

- **DPDP Act 2023 alignment**: data minimization (camera only records on trigger, nothing retained unless classified), purpose limitation, defined retention periods for evidence.
- **Chain of custody**: SHA-256 hashes generated at capture time for the video and every plate image, before any processing, to prove footage has not been altered — especially important for hit-and-run cases, where the video may be the sole evidentiary lead.
- **Restricted access**: only verified police accounts can view raw evidence or classify events — no public-facing access to personal data.
- **Dual-database separation**: keeping overspeeding and hit-and-run evidence in separate tables reflects their different legal tracks — one feeds an automated e-challan process, the other feeds active investigation, and conflating them risks improper handling of either.
- **Calibration note**: in a real deployment, radar/LiDAR units require certification for legal admissibility of both speed readings and any accident-detection claims; this is out of scope for the simulation but documented here for completeness.

---

## Analytics & Reporting

Once events are classified, the following insights can be generated from the two confirmed databases:

- **Overspeeding Hotspots** — event count grouped by `location_id` in `confirmed_overspeeding`, identifying zones needing more speed enforcement.
- **Accident/Hit-and-Run Hotspots** — event count grouped by `location_id` in `confirmed_hitandrun`, identifying zones needing physical patrol, better lighting, or road-design review.
- **Time-based Trends** — heatmaps by hour-of-day / day-of-week, separately for each case type.
- **Severity Distribution** — how far over the limit overspeeding events tend to be, per zone.
- **Repeat Plate Tracking** — frequency of the same plate appearing across either database, useful both for repeat-offender identification and for cross-referencing a hit-and-run plate against prior overspeeding events at the same location.

---

## Project Structure

```
project-root/
├── README.md
├── packet-tracer/
│   └── network-topology.pkt
├── backend/
│   ├── app.py / server.js
│   ├── routes/
│   ├── models/
│   └── auth/
├── database/
│   └── schema.sql
├── frontend/
│   ├── login.html
│   ├── review-queue.html      (video playback + classify controls)
│   ├── dashboard.html
│   └── analytics.html
├── cv-pipeline/ (mocked for simulation phase)
│   └── mock_anpr_generator.py
└── docs/
    └── architecture-diagrams/
```

---

## Setup Instructions

> To be expanded once implementation begins.

1. Clone/create the project directory structure above.
2. Set up the database using `database/schema.sql`.
3. Configure `.env` with database credentials and JWT secret (never commit secrets).
4. Run the backend server.
5. Open the Packet Tracer `.pkt` file to view/edit the simulated network topology.
6. Access the portal only from a machine within the simulated police VLAN.

---

## Roadmap

- [x] Design and build Packet Tracer network topology (VLANs, ACLs, HTTPS)
- [ ] Define and create database schema (`raw_event_queue`, `confirmed_overspeeding`, `confirmed_hitandrun`, `officer_accounts`)
- [ ] Build login + RBAC-secured backend
- [ ] Build case review portal with video playback + classify controls (Overspeeding / Hit-and-Run / Reject)
- [ ] Build analytics dashboard (separate hotspot views per case type)
- [ ] Mock ANPR/video event generator to simulate radar-triggered payloads
- [ ] Document chain-of-custody and DPDP compliance mapping
- [ ] (Stretch) Integrate e-challan SMS gateway mock for overspeeding notifications

---

## Disclaimer

This is an academic/prototype project. Cisco Packet Tracer is used to simulate network architecture and hardware placement; no real radar, camera, or ML inference hardware is used. Any resemblance to specific government portals (e.g., Parivahan/e-Challan) is for illustrative reference only.
