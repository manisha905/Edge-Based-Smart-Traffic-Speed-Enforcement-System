"""
SentinelGrid Backend — Configuration
All security-relevant values are environment-driven so nothing
sensitive is hardcoded in source. Copy .env.example to .env and
fill in real values before deploying.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).parent


def _env(key, default=None, cast=str):
    val = os.environ.get(key, default)
    if val is None:
        return None
    if cast is bool:
        return str(val).lower() in ("1", "true", "yes", "on")
    return cast(val)


class Config:
    # --- Core secrets ----------------------------------------------------
    # NEVER commit a real SECRET_KEY. This default only exists so the app
    # doesn't crash on first run; override it in .env for anything beyond
    # local testing.
    SECRET_KEY = _env("SECRET_KEY", "dev-only-change-me-before-deploying")

    # Pre-shared key the edge node must present when dispatching a trigger
    # payload. Stands in for the mTLS client-certificate check described
    # in the network design — in production this endpoint should sit
    # behind actual mutual TLS, with this key as a second, independent
    # factor rather than the only one.
    EDGE_API_KEY = _env("EDGE_API_KEY", "dev-only-edge-key-change-me")

    # --- Network-layer trust boundaries -----------------------------------
    # Only requests whose source IP falls in this range are allowed to
    # hit the ingestion endpoint at all — this mirrors the Packet Tracer
    # design where the edge-node subnet (172.16.x.x) is the only thing
    # permitted to reach the server's ingestion port via the router ACL.
    ALLOWED_EDGE_SUBNET = _env("ALLOWED_EDGE_SUBNET", "172.16.0.0/16")

    # Origins allowed to call this API from a browser (the portal's own
    # hostname/IP, nothing else). Comma-separated in .env.
    ALLOWED_ORIGINS = [
        o.strip() for o in _env(
            "ALLOWED_ORIGINS",
            "http://192.168.10.11,http://192.168.10.12,http://192.168.20.11,http://localhost:5000"
        ).split(",") if o.strip()
    ]

    # --- Session / token policy -------------------------------------------
    ACCESS_TOKEN_MINUTES = _env("ACCESS_TOKEN_MINUTES", 30, int)                 # hard cap per token
    SESSION_IDLE_TIMEOUT_MINUTES = _env("SESSION_IDLE_TIMEOUT_MINUTES", 10, int)  # matches login.html copy

    # --- OTP policy --------------------------------------------------------
    OTP_EXPIRY_SECONDS = _env("OTP_EXPIRY_SECONDS", 120, int)
    OTP_LENGTH = _env("OTP_LENGTH", 6, int)

    # --- Brute-force protection ---------------------------------------------
    MAX_FAILED_ATTEMPTS = _env("MAX_FAILED_ATTEMPTS", 5, int)
    FAILED_ATTEMPT_WINDOW_MINUTES = _env("FAILED_ATTEMPT_WINDOW_MINUTES", 15, int)
    LOCKOUT_MINUTES = _env("LOCKOUT_MINUTES", 30, int)

    # --- Misc ----------------------------------------------------------------
    AUTO_SEED_DEMO_DATA = _env("AUTO_SEED_DEMO_DATA", True, bool)
    PORT = _env("PORT", 5000, int)
    DEBUG = _env("DEBUG", False, bool)
