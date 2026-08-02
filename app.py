"""
SentinelGrid Backend — Application entrypoint

Run with:  python app.py
Serves the API that login.html / review-queue.html / dashboard.html /
analytics.html call into (once wired up — see README.md).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "database"))

from flask import Flask, jsonify, request

from config import Config
import db_helper


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # ---------------------------------------------------------------
    # Database bootstrap
    # ---------------------------------------------------------------
    db_helper.init_db(reset=False)  # idempotent — CREATE TABLE IF NOT EXISTS only

    _ensure_blocked_ips_table()

    if Config.AUTO_SEED_DEMO_DATA:
        _auto_seed_if_empty()

    # ---------------------------------------------------------------
    # CORS — hand-rolled and restrictive on purpose: only the exact
    # origins listed in Config.ALLOWED_ORIGINS may call this API from
    # a browser. This is deliberately not flask-cors' wildcard-by-
    # default behavior; every origin has to be explicitly enumerated,
    # matching the "police-only, nothing else" access model.
    # ---------------------------------------------------------------
    @app.after_request
    def apply_cors(response):
        origin = request.headers.get("Origin")
        if origin in Config.ALLOWED_ORIGINS:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Edge-API-Key"
            response.headers["Access-Control-Max-Age"] = "600"
        # Baseline hardening headers regardless of origin
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.route("/api/<path:_any>", methods=["OPTIONS"])
    def cors_preflight(_any):
        return ("", 204)

    # ---------------------------------------------------------------
    # Blueprints
    # ---------------------------------------------------------------
    from routes.auth_routes import auth_bp
    from routes.officer_routes import officer_bp
    from routes.admin_routes import admin_bp
    from routes.ingest_routes import ingest_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(officer_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(ingest_bp)

    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({"ok": True, "service": "sentinelgrid-backend"})

    return app


def _ensure_blocked_ips_table():
    conn = db_helper.get_connection()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS blocked_ips (
               ip TEXT PRIMARY KEY,
               blocked_at DATETIME,
               reason TEXT
           )"""
    )
    conn.commit()
    conn.close()


def _auto_seed_if_empty():
    """First-run convenience: if there are no officer accounts yet,
    seed the same demo accounts + demo events used throughout this
    project, so `python app.py` works immediately without a separate
    manual seeding step. Safe to run repeatedly — it only acts when
    the table is empty."""
    import security

    conn = db_helper.get_connection()
    count = conn.execute("SELECT COUNT(*) AS n FROM officer_accounts").fetchone()["n"]
    conn.close()
    if count > 0:
        return

    def add(officer_id, name, password, role, station, ip):
        conn = db_helper.get_connection()
        conn.execute(
            """INSERT OR REPLACE INTO officer_accounts
               (officer_id, full_name, password_hash, role, station_id, registered_ip)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (officer_id, name, security.hash_password(password), role, station, ip),
        )
        conn.commit()
        conn.close()

    add("officer1", "Insp. R. Kannan", "police123", "officer", "GANTRY-04", "192.168.10.11")
    add("officer2", "SI M. Bhavani", "police123", "officer", "GANTRY-04", "192.168.10.12")
    add("admin", "Supt. A. Verma", "admin123", "admin", "GANTRY-04 HQ", "192.168.20.11")

    db_helper.ingest_event(
        event_id="EVT-2026-00042", trigger_type="overspeed",
        location_id="Gantry-04 · NH-544", zone_coordinates="11.0168,76.9558",
        speed_detected=98, speed_limit=80,
        video_bytes_placeholder="video-content-evt42",
        plates=[
            {"plate_text": "TN38AB1234", "confidence_score": 0.94},
            {"plate_text": "TN22XY5678", "confidence_score": 0.88},
        ],
    )
    db_helper.ingest_event(
        event_id="EVT-2026-00043", trigger_type="accident",
        location_id="Gantry-04 · NH-544", zone_coordinates="11.0168,76.9558",
        speed_detected=None, speed_limit=None,
        video_bytes_placeholder="video-content-evt43",
        plates=[
            {"plate_text": "KA05CD7789", "confidence_score": 0.91},
            {"plate_text": "TN09EF4432", "confidence_score": 0.85},
        ],
    )
    print("[SentinelGrid] First run detected — seeded demo officer accounts and events.")


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=Config.PORT, debug=Config.DEBUG)
