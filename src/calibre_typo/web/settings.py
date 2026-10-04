from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..services import admin
from ..state import get_state
from .auth import _new_password_problem
from .security import log_in, login_required

bp = Blueprint("settings", __name__, url_prefix="/settings")


@bp.get("/")
@login_required
def index():
    return render_template("settings/index.html")


@bp.post("/password")
@login_required
def password():
    state = get_state()
    new, confirm = request.form.get("password", ""), request.form.get("confirm", "")
    with state.db.connect() as conn:
        current_ok = admin.verify_password(conn, request.form.get("current", ""))
    if not current_ok:
        flash("Wrong current password", "error")
    elif problem := _new_password_problem(new, confirm):
        flash(problem, "error")
    else:
        with state.db.connect() as conn:
            admin.set_password(conn, new)
        log_in()  # set_password ended every session, this one included
        flash("Password changed" if new else "Login turned off", "success")
    return redirect(url_for("settings.index"))
