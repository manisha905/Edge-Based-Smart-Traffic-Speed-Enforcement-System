"""
Officer routes: GET /api/events/pending, POST /api/events/<id>/classify

These power review-queue.html. Both require a valid officer-role
session token (see decorators.require_auth).
"""

import sys
from pathlib import Path
from flask import Blueprint, request, jsonify, g

sys.path.insert(0, str(Path(__file__).parent.parent / "database"))
import db_helper  # noqa: E402

from routes.decorators import require_auth

officer_bp = Blueprint("officer", __name__, url_prefix="/api/events")

VALID_CLASSIFICATIONS = {"overspeed", "hitandrun", "reject"}


@officer_bp.route("/pending", methods=["GET"])
@require_auth(role="officer")
def pending_events():
    events = db_helper.get_pending_events()
    return jsonify({"ok": True, "events": events})


@officer_bp.route("/<event_id>/classify", methods=["POST"])
@require_auth(role="officer")
def classify(event_id):
    data = request.get_json(silent=True) or {}
    classification = data.get("classification")

    if classification not in VALID_CLASSIFICATIONS:
        return jsonify({
            "ok": False,
            "error": f"classification must be one of {sorted(VALID_CLASSIFICATIONS)}"
        }), 400

    result = db_helper.classify_event(event_id, classification, officer_id=g.officer_id)
    status_code = 200 if result.get("ok") else 400
    return jsonify(result), status_code
