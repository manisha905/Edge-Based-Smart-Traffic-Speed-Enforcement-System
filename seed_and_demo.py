"""
Builds sentinelgrid.db from schema.sql, seeds officer accounts matching
the portal's demo logins, ingests the same three mock events used in
review-queue.html, then runs the classify workflow on two of them to
prove the overspeeding / hit-and-run split actually works end to end.
"""

from db_helper import (
    init_db, add_officer, authenticate, ingest_event,
    get_pending_events, classify_event, get_hotspots, get_security_alerts,
)

print("=== 1. Building database from schema.sql ===")
init_db(reset=True)
print("Done.\n")

print("=== 2. Seeding officer accounts ===")
add_officer("officer1", "Insp. R. Kannan", "police123", "officer", "GANTRY-04", "192.168.10.11")
add_officer("officer2", "SI M. Bhavani", "police123", "officer", "GANTRY-04", "192.168.10.12")
add_officer("admin", "Supt. A. Verma", "admin123", "admin", "GANTRY-04 HQ", "192.168.20.11")
print("3 accounts created.\n")

print("=== 3. Simulating login attempts (matches dashboard.html alert feed) ===")
print(authenticate("officer1", "police123", "192.168.10.11"))   # success
print(authenticate("officer1", "police123", "203.0.113.88"))    # wrong IP -> blocked
print(authenticate("admin", "wrongpass", "192.168.20.11"))       # wrong password
print()

print("=== 4. Ingesting mock events from the edge node (same 3 as the portal demo) ===")
ingest_event(
    event_id="EVT-2026-00042", trigger_type="overspeed",
    location_id="Gantry-04 · NH-544", zone_coordinates="11.0168,76.9558",
    speed_detected=98, speed_limit=80,
    video_bytes_placeholder="video-content-evt42",
    plates=[
        {"plate_text": "TN38AB1234", "confidence_score": 0.94},
        {"plate_text": "TN22XY5678", "confidence_score": 0.88},
    ],
)
ingest_event(
    event_id="EVT-2026-00043", trigger_type="accident",
    location_id="Gantry-04 · NH-544", zone_coordinates="11.0168,76.9558",
    speed_detected=None, speed_limit=None,
    video_bytes_placeholder="video-content-evt43",
    plates=[
        {"plate_text": "KA05CD7789", "confidence_score": 0.91},
        {"plate_text": "TN09EF4432", "confidence_score": 0.85},
    ],
)
ingest_event(
    event_id="EVT-2026-00044", trigger_type="overspeed",
    location_id="Gantry-04 · NH-544", zone_coordinates="11.0168,76.9558",
    speed_detected=112, speed_limit=80,
    video_bytes_placeholder="video-content-evt44",
    plates=[{"plate_text": "TN38AB9981", "confidence_score": 0.97}],
)
print("3 events ingested into raw_event_queue.\n")

print("=== 5. Pending queue (what review-queue.html would fetch) ===")
for e in get_pending_events():
    print(f"  {e['event_id']} | {e['trigger_type']:9s} | {e['location_id']} | plates: "
          f"{[p['plate_text'] for p in e['plates']]}")
print()

print("=== 6. Officer classifies events via the portal ===")
r1 = classify_event("EVT-2026-00042", "overspeed", officer_id="officer1")
print("EVT-2026-00042 -> overspeed:", r1)
r2 = classify_event("EVT-2026-00043", "hitandrun", officer_id="officer1")
print("EVT-2026-00043 -> hitandrun:", r2)
print("EVT-2026-00044 left pending intentionally (still in queue).\n")

print("=== 7. Remaining pending queue after classification ===")
for e in get_pending_events():
    print(f"  {e['event_id']} | {e['trigger_type']} | still pending")
print()

print("=== 8. Evidence folder layout after classification ===")
import subprocess
print(subprocess.run(["find", "evidence", "-type", "f"], cwd=".", capture_output=True, text=True).stdout)

print("=== 9. Hotspot analytics (what analytics.html would query) ===")
print(get_hotspots())
print()

print("=== 10. Security alerts (what dashboard.html would query) ===")
for a in get_security_alerts():
    print(f"  [{a['severity'].upper()}] officer_id={a['officer_id']} ip={a['source_ip']} reason={a['reason']}")
