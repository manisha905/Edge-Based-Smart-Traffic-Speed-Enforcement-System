-- ============================================================
-- SentinelGrid: Evidence Database Schema
-- SQLite (portable — swap to PostgreSQL/MySQL for production
-- by adjusting AUTOINCREMENT -> SERIAL/AUTO_INCREMENT and
-- DATETIME defaults as needed)
-- ============================================================

PRAGMA foreign_keys = ON;

-- ------------------------------------------------------------
-- officer_accounts
-- Every login (officer or admin) and the device IP each one
-- is registered to. This is what the 2FA device-check in
-- login.html validates against.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS officer_accounts (
    officer_id      TEXT PRIMARY KEY,
    full_name       TEXT NOT NULL,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('officer', 'admin')),
    station_id      TEXT NOT NULL,
    registered_ip   TEXT NOT NULL,          -- bound device IP for this account
    last_login      DATETIME,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- raw_event_queue
-- Every trigger (overspeed OR accident) lands here first,
-- unclassified. Nothing here is legal evidence yet.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw_event_queue (
    event_id         TEXT PRIMARY KEY,
    trigger_type     TEXT NOT NULL CHECK (trigger_type IN ('overspeed', 'accident')),
    event_timestamp  DATETIME NOT NULL,
    location_id      TEXT NOT NULL,
    zone_coordinates TEXT,
    speed_detected   REAL,                   -- NULL for accident-only triggers
    speed_limit      REAL,                   -- NULL for accident-only triggers
    video_file_path  TEXT NOT NULL,           -- path/reference to the 5s clip
    video_hash       TEXT NOT NULL,           -- SHA-256 at capture time
    status           TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'classified_overspeeding',
                                           'classified_hitandrun', 'rejected')),
    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- detected_plates
-- Every plate the edge-node's ANPR pipeline found in a clip.
-- Normalized (one row per plate) since a single event can
-- have multiple vehicles in frame, especially accident events.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS detected_plates (
    plate_row_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id         TEXT NOT NULL REFERENCES raw_event_queue(event_id) ON DELETE CASCADE,
    plate_text       TEXT NOT NULL,
    confidence_score REAL NOT NULL,
    image_file_path  TEXT NOT NULL,
    image_hash       TEXT NOT NULL
);

-- ------------------------------------------------------------
-- confirmed_overspeeding
-- Populated only when an officer classifies an event as
-- overspeeding. Feeds e-challan dispatch + speed analytics.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS confirmed_overspeeding (
    event_id                TEXT PRIMARY KEY REFERENCES raw_event_queue(event_id),
    officer_id               TEXT NOT NULL REFERENCES officer_accounts(officer_id),
    confirmation_timestamp   DATETIME NOT NULL,
    location_id              TEXT NOT NULL,
    zone_coordinates         TEXT,
    speed_detected           REAL NOT NULL,
    plate_text               TEXT NOT NULL,      -- primary offending vehicle
    video_file_path          TEXT NOT NULL,
    action_taken             TEXT NOT NULL DEFAULT 'echallan_issued'
                                CHECK (action_taken IN ('echallan_issued', 'warning'))
);

-- ------------------------------------------------------------
-- confirmed_hitandrun
-- Populated only when an officer classifies an event as
-- hit-and-run. Feeds active investigation, NOT e-challan.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS confirmed_hitandrun (
    event_id                   TEXT PRIMARY KEY REFERENCES raw_event_queue(event_id),
    officer_id                  TEXT NOT NULL REFERENCES officer_accounts(officer_id),
    confirmation_timestamp      DATETIME NOT NULL,
    location_id                 TEXT NOT NULL,
    zone_coordinates            TEXT,
    video_file_path             TEXT NOT NULL,
    case_status                 TEXT NOT NULL DEFAULT 'open'
                                   CHECK (case_status IN ('open', 'under_investigation', 'closed')),
    investigating_officer_id    TEXT REFERENCES officer_accounts(officer_id)
);

-- ------------------------------------------------------------
-- login_attempts
-- Every login/auth attempt, success or fail — this is what
-- feeds the admin security-alerts feed in dashboard.html.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS login_attempts (
    attempt_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    officer_id     TEXT,                       -- may be NULL/unknown if ID doesn't exist
    source_ip      TEXT NOT NULL,
    attempt_time   DATETIME DEFAULT CURRENT_TIMESTAMP,
    success        INTEGER NOT NULL CHECK (success IN (0, 1)),
    reason         TEXT,                       -- 'unregistered_ip','bad_password','bad_otp','ok'
    severity       TEXT CHECK (severity IN ('low', 'medium', 'high'))
);

-- ------------------------------------------------------------
-- Indexes for the queries the portal actually runs
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_raw_status     ON raw_event_queue(status);
CREATE INDEX IF NOT EXISTS idx_raw_location   ON raw_event_queue(location_id);
CREATE INDEX IF NOT EXISTS idx_plates_event   ON detected_plates(event_id);
CREATE INDEX IF NOT EXISTS idx_overspeed_loc  ON confirmed_overspeeding(location_id);
CREATE INDEX IF NOT EXISTS idx_hitrun_loc     ON confirmed_hitandrun(location_id);
CREATE INDEX IF NOT EXISTS idx_login_ip       ON login_attempts(source_ip);
CREATE INDEX IF NOT EXISTS idx_login_success  ON login_attempts(success);
