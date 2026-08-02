"""
SentinelGrid — Database Helper Module
======================================
This is the layer a real Flask/Django backend would import and call.
It wraps the SQLite database defined in schema.sql and handles the
full lifecycle: a trigger event arriving from an edge node, an officer
reviewing it, and the resulting record + evidence files landing in the
correct confirmed table/folder.

Evidence files (video clips, plate crops) are stored on disk under
evidence/<status>/<event_id>/ ; the database stores paths + SHA-256
hashes, not the file bytes themselves — this keeps the DB small and
matches how a real deployment would use object storage (S3 등) or a
NAS for the actual media.
"""

import sqlite3
import hashlib
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "sentinelgrid.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"
EVIDENCE_DIR = BASE_DIR / "evidence"


# ------------------------------------------------------------------
# Setup
# ------------------------------------------------------------------

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(reset=False):
    """Create the database from schema.sql. reset=True wipes it first."""
    if reset and DB_PATH.exists():
        DB_PATH.unlink()
    conn = get_connection()
    with open(SCHEMA_PATH, "r") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()

    for sub in ("pending", "overspeeding", "hitandrun"):
        (EVIDENCE_DIR / sub).mkdir(parents=True, exist_ok=True)


def sha256_of_text(text: str) -> str:
    """Stand-in for hashing real video/image bytes at capture time.
    In production this hashes the actual file bytes on the edge node
    before transmission."""
    return hashlib.sha256(text.encode()).hexdigest()


# ------------------------------------------------------------------
# Officer accounts
# ------------------------------------------------------------------

def add_officer(officer_id, full_name, password_plain, role, station_id, registered_ip):
    """password_plain is hashed here — never store plaintext passwords."""
    pw_hash = hashlib.sha256(password_plain.encode()).hexdigest()
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO officer_accounts
           (officer_id, full_name, password_hash, role, station_id, registered_ip)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (officer_id, full_name, pw_hash, role, station_id, registered_ip),
    )
    conn.commit()
    conn.close()


def authenticate(officer_id, password_plain, source_ip):
    """Simulates the login.html flow: password check AND IP-binding check.
    Logs every attempt (success or fail) to login_attempts, which is what
    the admin dashboard's security-alerts feed reads from."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM officer_accounts WHERE officer_id = ?", (officer_id,)
    ).fetchone()

    pw_hash = hashlib.sha256(password_plain.encode()).hexdigest()

    if row is None:
        _log_attempt(conn, officer_id, source_ip, success=False,
                     reason="unknown_officer_id", severity="high")
        conn.close()
        return {"ok": False, "reason": "Officer ID not recognized."}

    if row["registered_ip"] != source_ip:
        _log_attempt(conn, officer_id, source_ip, success=False,
                     reason="unregistered_ip", severity="high")
        conn.close()
        return {"ok": False, "reason": "Login blocked: device IP does not match the "
                                        "registered terminal for this account."}

    if row["password_hash"] != pw_hash:
        _log_attempt(conn, officer_id, source_ip, success=False,
                     reason="bad_password", severity="medium")
        conn.close()
        return {"ok": False, "reason": "Incorrect password."}

    _log_attempt(conn, officer_id, source_ip, success=True, reason="ok", severity="low")
    conn.execute(
        "UPDATE officer_accounts SET last_login = ? WHERE officer_id = ?",
        (datetime.now(timezone.utc).isoformat(), officer_id),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "role": row["role"], "name": row["full_name"], "station": row["station_id"]}


def _log_attempt(conn, officer_id, source_ip, success, reason, severity):
    conn.execute(
        """INSERT INTO login_attempts (officer_id, source_ip, success, reason, severity)
           VALUES (?, ?, ?, ?, ?)""",
        (officer_id, source_ip, 1 if success else 0, reason, severity),
    )
    conn.commit()


# ------------------------------------------------------------------
# Ingestion — edge node -> raw_event_queue
# ------------------------------------------------------------------

def ingest_event(event_id, trigger_type, location_id, zone_coordinates,
                  speed_detected, speed_limit, video_bytes_placeholder, plates):
    """Simulates the edge node's dispatch step: a 5s clip + N detected
    plates arrive and land in raw_event_queue as 'pending'.

    plates: list of dicts like {"plate_text": "TN38AB1234", "confidence_score": 0.94,
                                 "image_bytes_placeholder": "..."}
    """
    conn = get_connection()

    event_dir = EVIDENCE_DIR / "pending" / event_id
    event_dir.mkdir(parents=True, exist_ok=True)

    video_path = event_dir / "clip.mp4.placeholder"
    video_path.write_text(video_bytes_placeholder)
    video_hash = sha256_of_text(video_bytes_placeholder)

    conn.execute(
        """INSERT INTO raw_event_queue
           (event_id, trigger_type, event_timestamp, location_id, zone_coordinates,
            speed_detected, speed_limit, video_file_path, video_hash, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
        (event_id, trigger_type, datetime.now(timezone.utc).isoformat(), location_id,
         zone_coordinates, speed_detected, speed_limit, str(video_path), video_hash),
    )

    for i, p in enumerate(plates):
        img_path = event_dir / f"plate_{i}_{p['plate_text']}.jpg.placeholder"
        img_path.write_text(p.get("image_bytes_placeholder", p["plate_text"]))
        img_hash = sha256_of_text(p.get("image_bytes_placeholder", p["plate_text"]))
        conn.execute(
            """INSERT INTO detected_plates
               (event_id, plate_text, confidence_score, image_file_path, image_hash)
               VALUES (?, ?, ?, ?, ?)""",
            (event_id, p["plate_text"], p["confidence_score"], str(img_path), img_hash),
        )

    conn.commit()
    conn.close()
    return {"event_id": event_id, "video_hash": video_hash, "status": "pending"}


def get_pending_events():
    """Powers review-queue.html's list."""
    conn = get_connection()
    events = conn.execute(
        "SELECT * FROM raw_event_queue WHERE status = 'pending' ORDER BY event_timestamp DESC"
    ).fetchall()
    result = []
    for e in events:
        plates = conn.execute(
            "SELECT plate_text, confidence_score FROM detected_plates WHERE event_id = ?",
            (e["event_id"],),
        ).fetchall()
        result.append({**dict(e), "plates": [dict(p) for p in plates]})
    conn.close()
    return result


# ------------------------------------------------------------------
# Classification — officer confirms via the portal
# ------------------------------------------------------------------

def classify_event(event_id, classification, officer_id):
    """classification: 'overspeed' | 'hitandrun' | 'reject'
    This is what fires when an officer clicks a button in review-queue.html.
    Moves the DB row into the right confirmed table AND moves the evidence
    files from evidence/pending/ into evidence/overspeeding/ or evidence/hitandrun/."""
    conn = get_connection()
    event = conn.execute(
        "SELECT * FROM raw_event_queue WHERE event_id = ?", (event_id,)
    ).fetchone()
    if event is None:
        conn.close()
        return {"ok": False, "reason": "Event not found."}
    if event["status"] != "pending":
        conn.close()
        return {"ok": False, "reason": f"Event already classified as {event['status']}."}

    now = datetime.now(timezone.utc).isoformat()
    old_dir = EVIDENCE_DIR / "pending" / event_id

    if classification == "reject":
        conn.execute(
            "UPDATE raw_event_queue SET status = 'rejected' WHERE event_id = ?", (event_id,)
        )
        conn.commit()
        conn.close()
        return {"ok": True, "filed_to": None, "note": "No case filed; queue entry closed."}

    if classification == "overspeed":
        target_folder = "overspeeding"
        primary_plate = conn.execute(
            "SELECT plate_text FROM detected_plates WHERE event_id = ? "
            "ORDER BY confidence_score DESC LIMIT 1", (event_id,)
        ).fetchone()
        new_video_path = str(EVIDENCE_DIR / target_folder / event_id / "clip.mp4.placeholder")
        conn.execute(
            """INSERT INTO confirmed_overspeeding
               (event_id, officer_id, confirmation_timestamp, location_id, zone_coordinates,
                speed_detected, plate_text, video_file_path, action_taken)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'echallan_issued')""",
            (event_id, officer_id, now, event["location_id"], event["zone_coordinates"],
             event["speed_detected"], primary_plate["plate_text"] if primary_plate else None,
             new_video_path),
        )
        conn.execute(
            "UPDATE raw_event_queue SET status = 'classified_overspeeding' WHERE event_id = ?",
            (event_id,),
        )

    elif classification == "hitandrun":
        target_folder = "hitandrun"
        new_video_path = str(EVIDENCE_DIR / target_folder / event_id / "clip.mp4.placeholder")
        conn.execute(
            """INSERT INTO confirmed_hitandrun
               (event_id, officer_id, confirmation_timestamp, location_id, zone_coordinates,
                video_file_path, case_status)
               VALUES (?, ?, ?, ?, ?, ?, 'open')""",
            (event_id, officer_id, now, event["location_id"], event["zone_coordinates"],
             new_video_path),
        )
        conn.execute(
            "UPDATE raw_event_queue SET status = 'classified_hitandrun' WHERE event_id = ?",
            (event_id,),
        )
    else:
        conn.close()
        return {"ok": False, "reason": f"Unknown classification '{classification}'."}

    # move the actual evidence files on disk
    new_dir = EVIDENCE_DIR / target_folder / event_id
    if old_dir.exists():
        new_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old_dir), str(new_dir))

    conn.commit()
    conn.close()
    return {"ok": True, "filed_to": f"confirmed_{('overspeeding' if classification=='overspeed' else 'hitandrun')}",
            "evidence_path": str(new_dir)}


# ------------------------------------------------------------------
# Analytics — powers analytics.html
# ------------------------------------------------------------------

def get_hotspots(limit=10):
    conn = get_connection()
    speed = conn.execute(
        """SELECT location_id, COUNT(*) AS n FROM confirmed_overspeeding
           GROUP BY location_id ORDER BY n DESC LIMIT ?""", (limit,)
    ).fetchall()
    hitrun = conn.execute(
        """SELECT location_id, COUNT(*) AS n FROM confirmed_hitandrun
           GROUP BY location_id ORDER BY n DESC LIMIT ?""", (limit,)
    ).fetchall()
    conn.close()
    return {
        "top_overspeeding_zones": [dict(r) for r in speed],
        "top_hitandrun_zones": [dict(r) for r in hitrun],
    }


def get_security_alerts(limit=20):
    """Powers dashboard.html's alert feed."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM login_attempts WHERE success = 0
           ORDER BY attempt_time DESC LIMIT ?""", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_active_officer_ips():
    conn = get_connection()
    rows = conn.execute(
        "SELECT officer_id, full_name, station_id, registered_ip, last_login "
        "FROM officer_accounts WHERE last_login IS NOT NULL ORDER BY last_login DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
