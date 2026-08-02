"""
Auth routes: POST /api/auth/login, POST /api/auth/verify-otp, POST /api/auth/logout

Two-stage login mirrors login.html:
  Stage 1 (login):      officer_id + password, checked ALONGSIDE the
                         request's source IP against the account's
                         registered device IP. Both must match before
                         we even issue an OTP.
  Stage 2 (verify-otp):  the one-time code, single-use and short-lived.

Every attempt — success or failure, at either stage — is logged to
login_attempts, which is what powers the admin dashboard's security
alert feed.
"""

import sys
from pathlib import Path
from flask import Blueprint, request, jsonify

sys.path.insert(0, str(Path(__file__).parent.parent / "database"))
import db_helper  # noqa: E402

import security
from config import Config

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _log(conn, officer_id, ip, success, reason, severity):
    conn.execute(
        """INSERT INTO login_attempts (officer_id, source_ip, success, reason, severity)
           VALUES (?, ?, ?, ?, ?)""",
        (officer_id, ip, 1 if success else 0, reason, severity),
    )
    conn.commit()


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    officer_id = (data.get("officer_id") or "").strip()
    password = data.get("password") or ""

    # The device's real IP should come from the TCP connection itself
    # (request.remote_addr), or from a trusted reverse-proxy header if
    # this app sits behind nginx/VPN termination as designed. We do
    # NOT trust a client-supplied IP field for the actual security
    # decision — request.remote_addr is authoritative here.
    request_ip = request.remote_addr

    if not officer_id or not password:
        return jsonify({"ok": False, "error": "Officer ID and password are required."}), 400

    conn = db_helper.get_connection()

    if security.is_ip_blocked(conn, request_ip):
        _log(conn, officer_id, request_ip, False, "blocked_ip", "high")
        conn.close()
        return jsonify({"ok": False, "error": "Access denied from this network location."}), 403

    failed_count = security.recent_failed_attempts(
        conn, officer_id, request_ip, Config.FAILED_ATTEMPT_WINDOW_MINUTES
    )
    if failed_count >= Config.MAX_FAILED_ATTEMPTS:
        security.block_ip(conn, request_ip, reason="exceeded max failed login attempts")
        _log(conn, officer_id, request_ip, False, "lockout_triggered", "high")
        conn.close()
        return jsonify({
            "ok": False,
            "error": f"Too many failed attempts. This device is temporarily blocked for "
                     f"{Config.LOCKOUT_MINUTES} minutes."
        }), 429

    row = conn.execute(
        "SELECT * FROM officer_accounts WHERE officer_id = ?", (officer_id,)
    ).fetchone()

    # Deliberately generic client-facing error regardless of *which*
    # check failed (unknown ID vs wrong password vs wrong device) —
    # avoids leaking which piece of information was wrong. The FULL
    # reason is still recorded in login_attempts for the admin feed.
    generic_error = "Invalid credentials, or this device is not authorized for this account."

    if row is None:
        _log(conn, officer_id, request_ip, False, "unknown_officer_id", "high")
        conn.close()
        return jsonify({"ok": False, "error": generic_error}), 401

    if row["registered_ip"] != request_ip:
        _log(conn, officer_id, request_ip, False, "unregistered_ip", "high")
        conn.close()
        return jsonify({"ok": False, "error": generic_error}), 401

    if not security.verify_password(password, row["password_hash"]):
        _log(conn, officer_id, request_ip, False, "bad_password", "medium")
        conn.close()
        return jsonify({"ok": False, "error": generic_error}), 401

    # Password + device both check out — issue the second factor.
    code = security.issue_otp(officer_id)
    conn.close()

    # NOTE: in production, dispatch `code` via SMS/authenticator app —
    # never return it in the API response. We print it server-side so
    # the demo is testable without a real SMS gateway wired up.
    print(f"[DEMO OTP] officer_id={officer_id} code={code} "
          f"(expires in {Config.OTP_EXPIRY_SECONDS}s)")

    return jsonify({"ok": True, "stage": "otp_required", "officer_id": officer_id})


@auth_bp.route("/verify-otp", methods=["POST"])
def verify_otp():
    data = request.get_json(silent=True) or {}
    officer_id = (data.get("officer_id") or "").strip()
    otp = (data.get("otp") or "").strip()
    request_ip = request.remote_addr

    conn = db_helper.get_connection()

    if security.is_ip_blocked(conn, request_ip):
        conn.close()
        return jsonify({"ok": False, "error": "Access denied from this network location."}), 403

    if not security.verify_otp(officer_id, otp):
        _log(conn, officer_id, request_ip, False, "bad_otp", "high")
        failed_count = security.recent_failed_attempts(
            conn, officer_id, request_ip, Config.FAILED_ATTEMPT_WINDOW_MINUTES
        )
        if failed_count >= Config.MAX_FAILED_ATTEMPTS:
            security.block_ip(conn, request_ip, reason="exceeded max failed OTP attempts")
        conn.close()
        return jsonify({"ok": False, "error": "Incorrect or expired one-time code."}), 401

    row = conn.execute(
        "SELECT * FROM officer_accounts WHERE officer_id = ?", (officer_id,)
    ).fetchone()
    if row is None:
        conn.close()
        return jsonify({"ok": False, "error": "Account not found."}), 404

    _log(conn, officer_id, request_ip, True, "ok", "low")
    conn.execute(
        "UPDATE officer_accounts SET last_login = CURRENT_TIMESTAMP WHERE officer_id = ?",
        (officer_id,),
    )
    conn.commit()
    conn.close()

    session = security.issue_token(
        officer_id=row["officer_id"], role=row["role"],
        station_id=row["station_id"], ip=request_ip,
    )

    return jsonify({
        "ok": True,
        "token": session["token"],
        "expires_in_minutes": session["expires_in_minutes"],
        "role": row["role"],
        "name": row["full_name"],
        "station": row["station_id"],
    })


@auth_bp.route("/logout", methods=["POST"])
def logout():
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        ok, result = security.decode_and_validate(token, request.remote_addr)
        if ok:
            security.revoke_session(result["jti"])
    return jsonify({"ok": True})
