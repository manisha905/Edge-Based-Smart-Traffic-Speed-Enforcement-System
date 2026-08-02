"""
SentinelGrid Backend — Security primitives
============================================
Everything auth-related lives here so the routes stay thin and every
security decision is in one auditable place.

Implements:
  - Password hashing (PBKDF2-SHA256 via werkzeug — never plaintext)
  - OTP generation/verification (second factor, short-lived, single-use)
  - JWT session issuance + server-side idle-timeout enforcement
  - IP allowlist / blocklist checks
  - Brute-force detection (failed-attempt counting + auto-lockout)

Note on in-memory stores: OTP codes and live sessions are kept in a
process-local dict for this reference implementation. That's fine for
a single-process demo/deployment; a production multi-worker deployment
should move both to Redis (with native TTL support) so state is shared
across workers and survives restarts.
"""

import time
import random
import string
import ipaddress
import uuid
from datetime import datetime, timezone

import jwt
from werkzeug.security import generate_password_hash, check_password_hash

from config import Config

# ------------------------------------------------------------------
# In-memory ephemeral stores (see module docstring)
# ------------------------------------------------------------------
_otp_store = {}      # officer_id -> {"code": str, "expires": float, "used": bool}
_sessions = {}        # jti -> {"officer_id","role","station","ip","last_activity": float}


# ------------------------------------------------------------------
# Password hashing
# ------------------------------------------------------------------

def hash_password(plain: str) -> str:
    return generate_password_hash(plain, method="pbkdf2:sha256", salt_length=16)


def verify_password(plain: str, stored_hash: str) -> bool:
    try:
        return check_password_hash(stored_hash, plain)
    except ValueError:
        return False


# ------------------------------------------------------------------
# OTP (second factor)
# ------------------------------------------------------------------

def issue_otp(officer_id: str) -> str:
    """Generates and stores a fresh OTP. Returns the code so the caller
    can dispatch it via SMS/authenticator app — this function does NOT
    put the code in any HTTP response. In this reference build we log
    it server-side (see auth_routes) purely so the demo is usable
    without a real SMS gateway wired up."""
    code = "".join(random.choices(string.digits, k=Config.OTP_LENGTH))
    _otp_store[officer_id] = {
        "code": code,
        "expires": time.time() + Config.OTP_EXPIRY_SECONDS,
        "used": False,
    }
    return code


def verify_otp(officer_id: str, submitted: str) -> bool:
    entry = _otp_store.get(officer_id)
    if not entry:
        return False
    if entry["used"]:
        return False
    if time.time() > entry["expires"]:
        return False
    if entry["code"] != submitted:
        return False
    entry["used"] = True  # single-use
    return True


# ------------------------------------------------------------------
# JWT session issuance + idle-timeout enforcement
# ------------------------------------------------------------------

def issue_token(officer_id: str, role: str, station_id: str, ip: str) -> dict:
    jti = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    payload = {
        "sub": officer_id,
        "role": role,
        "station": station_id,
        "ip": ip,                # bound at issuance; checked again per-request
        "jti": jti,
        "iat": now,
        "exp": now.timestamp() + Config.ACCESS_TOKEN_MINUTES * 60,
    }
    token = jwt.encode(payload, Config.SECRET_KEY, algorithm="HS256")
    _sessions[jti] = {
        "officer_id": officer_id,
        "role": role,
        "station": station_id,
        "ip": ip,
        "last_activity": time.time(),
    }
    return {"token": token, "jti": jti, "expires_in_minutes": Config.ACCESS_TOKEN_MINUTES}


def decode_and_validate(token: str, request_ip: str):
    """Returns (ok, payload_or_error_message). Checks, in order:
    signature/expiry, session still live server-side, idle timeout,
    and that the request's source IP still matches the IP the session
    was issued to (defense-in-depth against a stolen/replayed token
    being used from a different machine)."""
    try:
        payload = jwt.decode(token, Config.SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return False, "Session token expired."
    except jwt.InvalidTokenError:
        return False, "Invalid session token."

    jti = payload.get("jti")
    session = _sessions.get(jti)
    if session is None:
        return False, "Session not recognized or already logged out."

    idle_seconds = time.time() - session["last_activity"]
    if idle_seconds > Config.SESSION_IDLE_TIMEOUT_MINUTES * 60:
        _sessions.pop(jti, None)
        return False, "Session expired due to inactivity."

    if session["ip"] != request_ip:
        # The token is being replayed from a different IP than it was
        # issued to — treat this as a hijack attempt, kill the session.
        _sessions.pop(jti, None)
        return False, "Session invalidated: request origin changed."

    session["last_activity"] = time.time()
    return True, payload


def revoke_session(jti: str):
    _sessions.pop(jti, None)


def list_live_sessions():
    return [{"jti": k, **v} for k, v in _sessions.items()]


# ------------------------------------------------------------------
# IP allowlist (edge-node ingestion) / blocklist (abusive clients)
# ------------------------------------------------------------------

def ip_in_subnet(ip: str, subnet: str) -> bool:
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network(subnet, strict=False)
    except ValueError:
        return False


def is_ip_blocked(conn, ip: str) -> bool:
    row = conn.execute("SELECT 1 FROM blocked_ips WHERE ip = ?", (ip,)).fetchone()
    return row is not None


def block_ip(conn, ip: str, reason: str):
    conn.execute(
        "INSERT OR REPLACE INTO blocked_ips (ip, blocked_at, reason) VALUES (?, ?, ?)",
        (ip, datetime.now(timezone.utc).isoformat(), reason),
    )
    conn.commit()


def unblock_ip(conn, ip: str):
    conn.execute("DELETE FROM blocked_ips WHERE ip = ?", (ip,))
    conn.commit()


# ------------------------------------------------------------------
# Brute-force detection
# ------------------------------------------------------------------

def recent_failed_attempts(conn, officer_id: str, ip: str, window_minutes: int) -> int:
    row = conn.execute(
        """SELECT COUNT(*) AS n FROM login_attempts
           WHERE success = 0
             AND attempt_time >= datetime('now', ?)
             AND (officer_id = ? OR source_ip = ?)""",
        (f"-{window_minutes} minutes", officer_id, ip),
    ).fetchone()
    return row["n"] if row else 0
