"""
Admin routes: sessions, security alerts, IP blocking, hotspot analytics.
Power dashboard.html and analytics.html. All require admin-role token.
"""

import sys
from pathlib import Path
from flask import Blueprint, request, jsonify

sys.path.insert(0, str(Path(__file__).parent.parent / "database"))
import db_helper  # noqa: E402

import security
from routes.decorators import require_auth

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


# ------------------------------------------------------------------
# Active sessions (which officer PCs are currently logged in + IP)
# ------------------------------------------------------------------

@admin_bp.route("/sessions", methods=["GET"])
@require_auth(role="admin")
def sessions():
    live = security.list_live_sessions()
    return jsonify({"ok": True, "active_sessions": live})


# ------------------------------------------------------------------
# Security alerts (failed logins, lockouts, IP mismatches, etc.)
# ------------------------------------------------------------------

_REASON_LABELS = {
    "unknown_officer_id": ("Login attempt with unrecognized officer ID", "high"),
    "unregistered_ip": ("Login attempt from unregistered device IP", "high"),
    "bad_password": ("Incorrect password submitted", "medium"),
    "bad_otp": ("Incorrect or expired one-time code submitted", "high"),
    "lockout_triggered": ("Repeated failed logins — device auto-blocked", "high"),
    "blocked_ip": ("Login attempt from an already-blocked device", "medium"),
}


@admin_bp.route("/alerts", methods=["GET"])
@require_auth(role="admin")
def alerts():
    conn = db_helper.get_connection()
    rows = conn.execute(
        """SELECT * FROM login_attempts WHERE success = 0
           ORDER BY attempt_time DESC LIMIT 50"""
    ).fetchall()
    conn.close()

    out = []
    for r in rows:
        label, sev = _REASON_LABELS.get(r["reason"], (r["reason"] or "Unknown event", "low"))
        out.append({
            "attempt_id": r["attempt_id"],
            "officer_id": r["officer_id"],
            "source_ip": r["source_ip"],
            "time": r["attempt_time"],
            "title": label,
            "severity": r["severity"] or sev,
            "reason_code": r["reason"],
        })
    return jsonify({"ok": True, "alerts": out})


@admin_bp.route("/alerts/block-ip", methods=["POST"])
@require_auth(role="admin")
def block_ip():
    data = request.get_json(silent=True) or {}
    ip = data.get("ip")
    reason = data.get("reason", "blocked by admin")
    if not ip:
        return jsonify({"ok": False, "error": "ip is required"}), 400
    conn = db_helper.get_connection()
    security.block_ip(conn, ip, reason)
    conn.close()
    return jsonify({"ok": True, "blocked_ip": ip})


@admin_bp.route("/alerts/unblock-ip", methods=["POST"])
@require_auth(role="admin")
def unblock_ip():
    data = request.get_json(silent=True) or {}
    ip = data.get("ip")
    if not ip:
        return jsonify({"ok": False, "error": "ip is required"}), 400
    conn = db_helper.get_connection()
    security.unblock_ip(conn, ip)
    conn.close()
    return jsonify({"ok": True, "unblocked_ip": ip})


# ------------------------------------------------------------------
# Analytics (nationwide hotspot data — analytics.html)
# ------------------------------------------------------------------

@admin_bp.route("/analytics/hotspots", methods=["GET"])
@require_auth(role="admin")
def hotspots():
    limit = request.args.get("limit", default=10, type=int)
    data = db_helper.get_hotspots(limit=limit)
    return jsonify({"ok": True, **data})
