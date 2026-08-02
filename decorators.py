"""
Route-protection decorator. Wraps any endpoint that requires a valid
session token, optionally restricted to a specific role (RBAC).
"""

from functools import wraps
from flask import request, jsonify, g

import security


def require_auth(role=None):
    """Usage: @require_auth() for any logged-in user,
    @require_auth(role='admin') to restrict to admins,
    @require_auth(role='officer') to restrict to officers."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return jsonify({"ok": False, "error": "Missing or malformed Authorization header."}), 401

            token = auth_header.split(" ", 1)[1].strip()
            request_ip = request.remote_addr

            ok, result = security.decode_and_validate(token, request_ip)
            if not ok:
                return jsonify({"ok": False, "error": result}), 401

            if role is not None and result.get("role") != role:
                return jsonify({"ok": False, "error": f"This endpoint requires the '{role}' role."}), 403

            # stash identity on flask.g for the route to use
            g.officer_id = result["sub"]
            g.role = result["role"]
            g.station = result["station"]
            g.jti = result["jti"]

            return fn(*args, **kwargs)
        return wrapper
    return decorator
