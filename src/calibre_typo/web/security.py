from __future__ import annotations

import ipaddress
import secrets
from collections.abc import Callable
from functools import wraps
from typing import TypeVar

from flask import abort, g, jsonify, redirect, request, session, url_for

from ..services import admin, devices
from ..state import get_state

F = TypeVar("F", bound=Callable)

PLUGIN_VERSION_HEADER = "X-Calibre-Typo-Plugin"
_CSRF_KEY = "csrf_token"


_SESSION_KEY = "sid"


def log_in() -> None:
    with get_state().db.connect() as conn:
        session_id = admin.start_session(conn)
    session.clear()
    session.permanent = True
    session[_SESSION_KEY] = session_id


def log_out() -> None:
    if session_id := session.get(_SESSION_KEY):
        with get_state().db.connect() as conn:
            admin.end_session(conn, session_id)
    session.clear()


def login_enabled() -> bool:
    with get_state().db.connect() as conn:
        return not admin.login_disabled(conn)


def is_logged_in() -> bool:
    session_id = session.get(_SESSION_KEY)
    with get_state().db.connect() as conn:
        if admin.login_disabled(conn):
            return True
        return bool(session_id) and admin.session_valid(conn, session_id)


def login_required(view: F) -> F:
    @wraps(view)
    def wrapper(*args, **kwargs):
        with get_state().db.connect() as conn:
            if not admin.is_set_up(conn):
                return redirect(url_for("auth.setup"))
        if not is_logged_in():
            return redirect(url_for("auth.login", next=request.full_path))
        return view(*args, **kwargs)
    return wrapper  # type: ignore[return-value]


def _is_local(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private


def client_address() -> str:
    """A private peer is a proxy: trust only the last X-Forwarded-For entry, as
    earlier ones can be forged. A public peer's header is ignored"""
    peer = request.remote_addr or ""
    if _is_local(peer):
        forwarded = request.headers.get("X-Forwarded-For", "").split(",")[-1].strip()
        try:
            return str(ipaddress.ip_address(forwarded))
        except ValueError:
            pass
    return peer or "unknown"


def csrf_token() -> str:
    if _CSRF_KEY not in session:
        session[_CSRF_KEY] = secrets.token_urlsafe(32)
    return session[_CSRF_KEY]


def check_csrf() -> None:
    if request.method != "POST" or request.blueprint == "api":
        return
    sent = request.form.get(_CSRF_KEY, "")
    expected = session.get(_CSRF_KEY, "")
    if not expected or not secrets.compare_digest(sent, expected):
        abort(400, "Form expired. Reload and try again.")


def device_required(view: F) -> F:
    @wraps(view)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        token = header.removeprefix("Bearer ").strip() if header.startswith("Bearer ") else ""
        device = None
        if token:
            with get_state().db.connect() as conn:
                device = devices.authenticate(conn, token, request.headers.get(PLUGIN_VERSION_HEADER))
        if device is None:
            return jsonify(error="invalid token"), 401
        g.device = device
        return view(*args, **kwargs)
    return wrapper  # type: ignore[return-value]
