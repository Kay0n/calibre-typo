from __future__ import annotations

import io
import re

from flask import (Blueprint, abort, flash, redirect, render_template, request,
                   send_file, session, url_for)

from ..services import devices, plugin_bundle
from ..state import get_state
from .security import login_required

bp = Blueprint("devices", __name__, url_prefix="/devices")

# The session cookie is readable, so it only holds a ticket
_TICKET_KEY = "issued_ticket"


def _remember_token(device_id: int, token: str) -> None:
    session[_TICKET_KEY] = get_state().issued_tokens.remember(device_id, token)


def _issued_token(device: devices.Device) -> str | None:
    if not device.active:
        return None
    return get_state().issued_tokens.get(session.get(_TICKET_KEY), device.id)


def _server_url() -> str:
    return get_state().settings.public_url or request.url_root.rstrip("/")


def _device_or_404(device_id: int) -> devices.Device:
    with get_state().db.connect() as conn:
        return devices.get_device(conn, device_id) or abort(404)


@bp.get("/")
@login_required
def index():
    state = get_state()
    with state.db.connect() as conn:
        rows = devices.list_devices(conn)
    return render_template("devices/index.html", devices=rows, latest_plugin=state.plugin_version)


@bp.post("/")
@login_required
def create():
    name = request.form.get("name", "").strip()[:60]
    if not name:
        flash("Device name required", "error")
        return redirect(url_for("devices.index"))
    with get_state().db.connect() as conn:
        device, token = devices.create_device(conn, name)
    _remember_token(device.id, token)
    return redirect(url_for("devices.install", device_id=device.id))


@bp.post("/<int:device_id>/reactivate")
@login_required
def reactivate(device_id: int):
    device = _device_or_404(device_id)
    with get_state().db.connect() as conn:
        token = devices.reactivate(conn, device_id)
    if not token:
        flash(f"{device.name} is already active", "error")
        return redirect(url_for("devices.index"))
    _remember_token(device_id, token)
    return redirect(url_for("devices.install", device_id=device_id))


@bp.post("/<int:device_id>/revoke")
@login_required
def revoke(device_id: int):
    device = _device_or_404(device_id)
    with get_state().db.connect() as conn:
        devices.revoke(conn, device_id)
    flash(f"{device.name} revoked", "info")
    return redirect(url_for("devices.index"))


@bp.post("/<int:device_id>/delete")
@login_required
def delete(device_id: int):
    with get_state().db.connect() as conn:
        devices.delete(conn, device_id)
    return redirect(url_for("devices.index"))


@bp.get("/<int:device_id>/install")
@login_required
def install(device_id: int):
    device = _device_or_404(device_id)
    return render_template("devices/install.html", device=device,
                           token=_issued_token(device), server_url=_server_url(),
                           public_url_set=bool(get_state().settings.public_url))


@bp.get("/<int:device_id>/plugin.zip")
@login_required
def plugin_zip(device_id: int):
    device = _device_or_404(device_id)
    token = _issued_token(device)
    if not token:
        flash("Download expired. Revoke and reactivate the device for a new one.", "error")
        return redirect(url_for("devices.index"))
    data = plugin_bundle.build_zip(get_state().settings.plugin_dir, _server_url(), token, device.name)
    slug = re.sub(r"[^A-Za-z0-9]+", "-", device.name).strip("-").lower() or "device"
    return send_file(io.BytesIO(data), mimetype="application/zip", as_attachment=True,
                     download_name=f"calibretypo-{slug}.zip")
