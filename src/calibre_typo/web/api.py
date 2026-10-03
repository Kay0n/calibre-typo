from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from ..services import edits
from ..state import get_state
from .security import device_required

bp = Blueprint("api", __name__, url_prefix="/api/v1")

MAX_EDITS_PER_REQUEST = 500


def _envelope(**payload):
    return jsonify(plugin_version=get_state().plugin_version, **payload)


@bp.get("/ping")
@device_required
def ping():
    return _envelope(ok=True, device=g.device.name)


@bp.post("/edits")
@device_required
def submit_edits():
    body = request.get_json(silent=True)
    submitted = body.get("edits") if isinstance(body, dict) else None
    if not isinstance(submitted, list):
        return jsonify(error="expected {\"edits\": [...]}"), 400
    submitted = [e for e in submitted[:MAX_EDITS_PER_REQUEST] if isinstance(e, dict)]

    state = get_state()
    with state.db.connect() as conn:
        accepted = edits.receive(conn, state.library, g.device.id, submitted)
    return _envelope(accepted=accepted)
