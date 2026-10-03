from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..library import suggest
from ..services import edits, review
from ..state import get_state
from .filters import fixes
from .security import login_required

bp = Blueprint("review", __name__)


@bp.get("/")
@login_required
def index():
    state = get_state()
    books = state.library.books()
    with state.db.connect() as conn:
        edits.release_missing_books(conn, {b.id for b in books})
        summaries = edits.book_summaries(conn, books)
        unmatched = edits.unmatched_count(conn)
    return render_template("review/index.html", summaries=summaries, unmatched=unmatched)


@bp.get("/books/<int:book_id>")
@login_required
def book(book_id: int):
    state = get_state()
    found = state.library.book(book_id) or abort(404)
    with state.db.connect() as conn:
        items = review.review_items(conn, found)
    return render_template("review/book.html", book=found, items=items)


@bp.post("/books/<int:book_id>")
@login_required
def decide(book_id: int):
    state = get_state()
    found = state.library.book(book_id) or abort(404)

    if "reopen" in request.form:
        if request.form["reopen"].isdigit():
            with state.db.connect() as conn:
                edits.reopen(conn, book_id, int(request.form["reopen"]))
        return redirect(url_for("review.book", book_id=book_id))

    approve, reject = [], []
    with state.db.connect() as conn:
        for key, decision in request.form.items():
            edit_id = key.removeprefix("decision-")
            if not key.startswith("decision-") or not edit_id.isdigit():
                continue
            edit_id = int(edit_id)
            replacement = request.form.get(f"replacement-{edit_id}")
            if replacement is not None:
                edits.set_replacement(conn, book_id, edit_id, replacement)
            if decision == "approve":
                approve.append(edit_id)
            elif decision == "reject":
                reject.append(edit_id)
        edits.reject(conn, book_id, reject)

    if approve:
        try:
            outcome = review.apply_fixes(state.db, state.library, state.settings.backups_dir, found, approve)
        except review.BookUnavailable as err:
            flash(str(err), "error")
        else:
            if outcome.applied:
                flash(f"Applied {fixes(len(outcome.applied))}", "success")
            for edit_id, error in outcome.failed.items():
                flash(f"Fix #{edit_id} failed: {error}", "error")
    if reject:
        flash(f"Rejected {fixes(len(reject))}", "info")
    return redirect(url_for("review.book", book_id=book_id))


@bp.route("/unmatched", methods=["GET", "POST"])
@login_required
def unmatched():
    state = get_state()
    if request.method == "POST":
        book_ids = {b.id for b in state.library.books()}
        with state.db.connect() as conn:
            for key, value in request.form.items():
                edit_id = key.partition("-")[2]
                if not edit_id.isdigit():
                    continue
                if key.startswith("book-") and value.isdigit() and int(value) in book_ids:
                    edits.assign_book(conn, int(edit_id), int(value))
                elif key.startswith("discard-") and value:
                    edits.discard_unmatched(conn, int(edit_id))
        flash("Saved", "success")
        return redirect(url_for("review.unmatched"))

    with state.db.connect() as conn:
        rows = edits.unmatched(conn)
    books = state.library.books() if rows else []
    suggestions = {r["id"]: suggest(books, title=r["book_title"], filename=r["filename"]) for r in rows}
    return render_template("review/unmatched.html", edits=rows, books=books, suggestions=suggestions)
