# Edge-Based ANPR & Speed Enforcement System

A privacy-compliant, event-driven speed enforcement architecture combining roadside radar triggers, edge computing, secure networking, and a police-only verification portal with violation analytics.

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

This project simulates an **automated speed enforcement system** used at traffic gantries. A radar/LiDAR sensor detects vehicle speed; if a violation is detected, a camera captures evidence, an edge device extracts the license plate via OCR, and the event is transmitted securely to a central server. A **restricted, police-only web portal** allows authorized officials to review evidence and confirm or reject each case. Confirmed violations are stored in a database and used to generate **accident-prone zone analytics**, helping direct future police enforcement to high-risk locations.

The system is designed around three core principles:

1. **Data Minimization** — non-violation data is discarded immediately; nothing is stored unless a threshold is breached.
2. **Restricted Access** — only authenticated, authorized police officials can access the verification portal or violation database. The public never interacts with the system directly.
3. **Evidentiary Integrity** — every captured image is hashed at the point of capture to preserve a tamper-proof chain of custody for legal use.

---

## System Roles & Access Control

| Role | Access Level | Capabilities |
|---|---|---|
| **Radar/Camera Edge Node** (simulated) | No portal access | Sends encrypted violation payloads only; cannot read/query the database |
| **Police Official (Verifier)** | Authenticated login | View pending violations, review evidence, confirm/reject cases, add remarks |
| **Admin** | Authenticated login (elevated) | Manage officer accounts, configure zone speed thresholds, view analytics dashboard, audit logs |
| **Vehicle Owner / Public** | **No access** | Receives only the final SMS/e-challan notice; never touches the system |

Access to the portal is restricted at both the **application layer** (login + Role-Based Access Control) and the **network layer** (VLAN segmentation + ACLs in Packet Tracer, so unauthorized subnets cannot even reach the portal's ports).

---

## System Architecture

```
 ┌───────────────────┐
 │  Radar / LiDAR      │  Continuous speed monitoring
 │  (Edge Sensor)      │
 └─────────┬───────────┘
           │ Speed > Threshold?
           ▼
 ┌───────────────────┐
 │  IR Camera Trigger  │  Context shot + Plate-cropped shot
 └─────────┬───────────┘
           ▼
 ┌───────────────────┐
 │  Edge Compute Node   │  YOLOv8 + OpenCV + OCR (PaddleOCR/Tesseract)
 │  (Jetson/RPi - sim)  │  SHA-256 hash at capture, encrypted payload
 └─────────┬───────────┘
           │ MQTT/HTTPS over mTLS + VPN tunnel
           ▼
 ┌───────────────────┐
 │  Central Server     │  Ingestion API → raw_violation_queue
 └─────────┬───────────┘
           ▼
 ┌───────────────────┐
 │  Police Portal       │  Login-restricted review interface
 │  (RBAC enforced)     │
 └─────────┬───────────┘
           │ Officer confirms case
           ▼
 ┌───────────────────┐
 │  confirmed_violations│ → SMS/e-challan dispatch (mocked)
 │  Database            │ → Feeds analytics dashboard
 └───────────────────┘
```

---

## Workflow

1. **Continuous Radar Monitoring** — Radar/LiDAR scans approaching traffic and measures vehicle speed via Doppler shift or laser reflection.
2. **Violation Triggering** — Edge computer compares detected speed to the zone's threshold. Compliant readings are discarded from RAM instantly.
3. **Image Capture & ANPR** — On violation, the IR camera captures a context shot and a plate-cropped shot.
4. **Edge OCR & Metadata Packaging** — YOLOv8 + OCR extract the plate string; speed, location ID, timestamp, and images are packaged into an encrypted payload with a SHA-256 hash.
5. **Secure Dispatch** — Payload is sent over MQTT/HTTPS via mTLS and VPN tunnel to the central server, landing in `raw_violation_queue`.
6. **Police Verification** — An authorized officer logs into the portal, reviews the evidence, and confirms or rejects the case.
7. **Confirmation & Notification** — Confirmed cases move to `confirmed_violations`, trigger an SMS/e-challan (mocked), and become part of the analytics dataset.
8. **Analytics** — Confirmed violations are aggregated by location and time to identify accident-prone zones requiring increased enforcement.

---

## Database Schema

Two tables separate **unverified** data from **verified, analytics-ready** data — this keeps OCR/radar errors out of official statistics.

### `raw_violation_queue` (pre-confirmation)

| Field | Type | Description |
|---|---|---|
| `violation_id` | UUID / PK | Unique event identifier |
| `timestamp` | DATETIME | Time of detection |
| `location_id` | VARCHAR | Gantry/zone identifier |
| `speed_detected` | FLOAT | Recorded speed (km/h) |
| `speed_limit` | FLOAT | Zone threshold at time of event |
| `plate_text_ocr` | VARCHAR | OCR-extracted plate string |
| `confidence_score` | FLOAT | OCR/detection confidence |
| `context_image_hash` | VARCHAR (SHA-256) | Hash of context image |
| `plate_image_hash` | VARCHAR (SHA-256) | Hash of plate-cropped image |
| `status` | ENUM | `pending` / `confirmed` / `rejected` |

### `confirmed_violations` (post-confirmation, analytics source)

| Field | Type | Description |
|---|---|---|
| `violation_id` | UUID / FK | References raw queue entry |
| `officer_id` | VARCHAR | ID of confirming official |
| `confirmation_timestamp` | DATETIME | When the case was confirmed |
| `location_id` | VARCHAR | Gantry/zone identifier |
| `zone_coordinates` | GEO / VARCHAR | Lat-long or descriptive location |
| `speed_detected` | FLOAT | Confirmed recorded speed |
| `plate_text` | VARCHAR | Verified plate string |
| `action_taken` | ENUM | `fine_issued` / `warning` / `escalated` |

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
| Roadside Edge Node | PC/Server or IoT "Thing" | Represents Jetson/RPi edge compute |
| Radar/Camera Sensors | Generic IoT sensor objects | Simulated event generators |
| Edge Gateway Router | Router | Simulates 4G/5G uplink to WAN |
| WAN Link | Cloud object | Simulates cellular/internet transport |
| Central Server | Server (HTTP/DB services) | Hosts ingestion API + police portal |
| Police Client PCs | PCs on a dedicated VLAN | Access portal only |
| Firewall/ACL Enforcement | Router ACLs | Restrict traffic by subnet/port |

### Key Design Requirements

- **VLAN Segmentation**: Police client subnet, edge-node ingestion subnet, and (if present) admin subnet are logically separated.
- **Access Control Lists (ACLs)**:
  - Edge node → allowed only to reach the server's ingestion API port.
  - Police subnet → allowed only to reach the portal's HTTP(S)/login port.
  - All other traffic → denied by default (deny-all fallback rule).
- **Simulated HTTPS**: Enable HTTP/HTTPS services on the Packet Tracer server object to demonstrate encrypted access to the portal.
- **Simulated VPN Tunnel**: Site-to-site VPN concept between the roadside router and central server's router, representing the real-world IPsec cellular VPN.

---

## Security Design

| Layer | Mechanism |
|---|---|
| Device Authentication | Mutual TLS (mTLS) between edge node and server |
| Data Integrity | SHA-256 hashing of raw images at capture time (chain of custody) |
| Transport Security | HTTPS/MQTT over TLS; VPN tunnel over cellular uplink |
| Application Access | Login + Role-Based Access Control (Officer vs Admin) |
| Network Access | VLAN segmentation + router ACLs restricting subnet-to-port access |
| Session Management | Token-based sessions (JWT) with auto-timeout |
| Audit Trail | Logging of every confirm/reject action with officer ID and timestamp |

---

## Tech Stack

**Computer Vision (simulated/mocked in this phase)**
- OpenCV — image preprocessing
- YOLOv8/v10 — vehicle & plate detection
- PaddleOCR / Tesseract — plate text extraction (fine-tuned for Indian plate formats)

**Backend / Portal**
- Python (Flask/Django) or Node.js (Express)
- JWT-based authentication, bcrypt password hashing
- REST API for ingestion + portal endpoints

**Database**
- PostgreSQL / MySQL (relational, supports the two-table verified/unverified split)

**Networking (Simulated)**
- Cisco Packet Tracer — topology, VLANs, ACLs, simulated VPN/HTTPS
- MQTT (Mosquitto) — lightweight edge telemetry
- HTTPS REST APIs — payload dispatch

**Frontend (Portal Dashboard)**
- HTML/CSS/JS or a lightweight framework (React) for the review UI and analytics charts

---

## Compliance & Legal Considerations

- **DPDP Act 2023 alignment**: data minimization (non-violation data discarded), purpose limitation, defined retention periods for evidence.
- **Chain of custody**: SHA-256 hashes generated at capture time, before any processing, to prove images have not been altered.
- **Restricted access**: only verified police accounts can view raw evidence or confirm violations — no public-facing access to personal data.
- **Calibration note**: in a real deployment, radar/LiDAR units require certification for legal admissibility of speed readings; this is out of scope for the simulation but documented here for completeness.

---

## Analytics & Reporting

Once violations are confirmed, the following insights can be generated from `confirmed_violations`:

- **Hotspot Identification** — violation count grouped by `location_id` to flag accident-prone zones.
- **Time-based Trends** — heatmaps by hour-of-day / day-of-week to identify when enforcement is most needed.
- **Severity Distribution** — how far over the limit violations tend to be, per zone (informs whether a zone needs physical patrol vs. camera-only monitoring).
- **Repeat Offender Tracking** — frequency of the same plate appearing across records.

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
│   ├── dashboard.html
│   └── analytics.html
├── cv-pipeline/ (mocked for simulation phase)
│   └── mock_ocr_generator.py
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

- [ ] Design and build Packet Tracer network topology (VLANs, ACLs, simulated VPN/HTTPS)
- [ ] Define and create database schema (`raw_violation_queue`, `confirmed_violations`, `officer_accounts`)
- [ ] Build login + RBAC-secured backend
- [ ] Build case review portal (pending violations → confirm/reject)
- [ ] Build analytics dashboard (hotspot maps, time trends)
- [ ] Mock CV/OCR event generator to simulate radar-triggered payloads
- [ ] Document chain-of-custody and DPDP compliance mapping
- [ ] (Stretch) Integrate SMS gateway mock for e-challan notification

---

## Disclaimer

This is an academic/prototype project. Cisco Packet Tracer is used to simulate network architecture and hardware placement; no real radar, camera, or ML inference hardware is used. Any resemblance to specific government portals (e.g., Parivahan/e-Challan) is for illustrative reference only.
