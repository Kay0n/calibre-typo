from __future__ import annotations

import logging

from urllib.parse import urlsplit

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..services import admin
from ..state import get_state
from .security import client_address, is_logged_in, log_in, log_out, login_required

log = logging.getLogger(__name__)
bp = Blueprint("auth", __name__)

TOO_MANY_ATTEMPTS = "Too many failed attempts. Try again later."


def _safe_next(target: str | None) -> str:
    # No open redirects. Browsers drop tabs and newlines and read "\" as "/"
    if target and target.startswith("/") and target.isprintable():
        as_browser_sees_it = target.replace("\\", "/")
        if not as_browser_sees_it.startswith("//") and not urlsplit(as_browser_sees_it).netloc:
            return target
    return url_for("review.index")


def _new_password_problem(password: str, confirm: str) -> str | None:
    if password != confirm:
        return "Passwords don't match"
    return None


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    state = get_state()
    with state.db.connect() as conn:
        if admin.is_set_up(conn):
            return redirect(url_for("auth.login"))

    if request.method == "POST":
        password, confirm = request.form.get("password", ""), request.form.get("confirm", "")
        if problem := _new_password_problem(password, confirm):
            flash(problem, "error")
        else:
            with state.db.connect() as conn:
                claimed = admin.claim(conn, password)
            if not claimed:
                return redirect(url_for("auth.login"))
            log.info("Admin password set; setup complete.")
            log_in()
            flash("Setup complete", "success")
            return redirect(url_for("devices.index"))
    return render_template("auth/setup.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    state = get_state()
    with state.db.connect() as conn:
        if not admin.is_set_up(conn):
            return redirect(url_for("auth.setup"))
    target = _safe_next(request.values.get("next"))
    if is_logged_in():
        return redirect(target)

    if request.method == "POST":
        client = client_address()
        if not state.login_throttle.allowed(client):
            flash(TOO_MANY_ATTEMPTS, "error")
        else:
            with state.db.connect() as conn:
                ok = admin.verify_password(conn, request.form.get("password", ""))
            if ok:
                state.login_throttle.succeeded(client)
                log_in()
                return redirect(target)
            state.login_throttle.failed(client)
            log.warning("Failed login from %s", client)
            flash("Wrong password", "error")
    return render_template("auth/login.html", next=target)


@bp.post("/logout")
def logout():
    log_out()
    return redirect(url_for("auth.login"))


@bp.route("/account", methods=["GET", "POST"])
@login_required
def account():
    if request.method == "POST":
        state = get_state()
        password, confirm = request.form.get("password", ""), request.form.get("confirm", "")
        with state.db.connect() as conn:
            current_ok = admin.verify_password(conn, request.form.get("current", ""))
        if not current_ok:
            flash("Wrong current password", "error")
        elif problem := _new_password_problem(password, confirm):
            flash(problem, "error")
        else:
            with state.db.connect() as conn:
                admin.set_password(conn, password)
            log_in()  # set_password ended every session, this one included
            flash("Password changed" if password else "Login turned off", "success")
            return redirect(url_for("auth.account"))
    return render_template("auth/account.html")
