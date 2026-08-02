"""
Ingestion route: POST /api/ingest/event

This is how the edge node (Edge-Node-PC in the network design) pushes
a trigger payload into raw_event_queue. It is intentionally NOT
protected by the officer/admin JWT system — it's machine-to-machine,
not a human login — and gets its own, stricter authentication:

  1. Source IP must fall within the edge-node subnet (172.16.0.0/16),
     mirroring the router ACL in the Packet Tracer design that only
     lets that subnet reach the ingestion port at all.
  2. A pre-shared API key must be present in X-Edge-API-Key, standing
     in for the mTLS client-certificate check described in the
     security design (production should use real mTLS here, with the
     API key as an additional, independent factor rather than the
     only one).

Neither the edge node's officer accounts nor its IP are ever granted
read access to the databases — this route is write-only/one-way,
matching the "edge node never touches the portal" requirement.
"""

import sys
from pathlib import Path
from flask import Blueprint, request, jsonify

sys.path.insert(0, str(Path(__file__).parent.parent / "database"))
import db_helper  # noqa: E402

import security
from config import Config

ingest_bp = Blueprint("ingest", __name__, url_prefix="/api/ingest")


@ingest_bp.route("/event", methods=["POST"])
def ingest_event():
    request_ip = request.remote_addr

    if not security.ip_in_subnet(request_ip, Config.ALLOWED_EDGE_SUBNET):
        return jsonify({
            "ok": False,
            "error": f"Source {request_ip} is outside the permitted edge-node subnet."
        }), 403

    api_key = request.headers.get("X-Edge-API-Key", "")
    if api_key != Config.EDGE_API_KEY:
        return jsonify({"ok": False, "error": "Invalid or missing edge API key."}), 401

    data = request.get_json(silent=True) or {}
    required = ["event_id", "trigger_type", "location_id", "video_content"]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"ok": False, "error": f"Missing required fields: {missing}"}), 400

    if data["trigger_type"] not in ("overspeed", "accident"):
        return jsonify({"ok": False, "error": "trigger_type must be 'overspeed' or 'accident'."}), 400

    plates = data.get("plates", [])
    normalized_plates = [
        {
            "plate_text": p["plate_text"],
            "confidence_score": p["confidence_score"],
            "image_bytes_placeholder": p.get("image_content", p["plate_text"]),
        }
        for p in plates
    ]

    result = db_helper.ingest_event(
        event_id=data["event_id"],
        trigger_type=data["trigger_type"],
        location_id=data["location_id"],
        zone_coordinates=data.get("zone_coordinates"),
        speed_detected=data.get("speed_detected"),
        speed_limit=data.get("speed_limit"),
        video_bytes_placeholder=data["video_content"],
        plates=normalized_plates,
    )
    return jsonify({"ok": True, **result}), 201
