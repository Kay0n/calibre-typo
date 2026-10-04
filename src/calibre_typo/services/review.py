from __future__ import annotations

import logging
import shutil
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..db import Database
from ..epub import EditNotApplicable, EpubDocument, Preview
from ..library import Book, CalibreLibrary
from . import edits

log = logging.getLogger(__name__)

# One writer at a time, so concurrent reviews can't overwrite each other
_apply_lock = threading.Lock()


class BookUnavailable(Exception):
    pass


@dataclass(frozen=True)
class ReviewItem:
    edit: sqlite3.Row
    preview: Preview | None = None
    problem: str | None = None

    @property
    def is_open(self) -> bool:
        return self.edit["status"] in edits.OPEN_STATUSES


@dataclass
class ApplyOutcome:
    applied: list[int] = field(default_factory=list)
    failed: dict[int, str] = field(default_factory=dict)


def _open_epub(book: Book) -> EpubDocument:
    if not book.epub or not book.epub.exists():
        raise BookUnavailable("No EPUB in the library")
    return EpubDocument(book.epub)


def review_items(conn: sqlite3.Connection, book: Book) -> list[ReviewItem]:
    rows = edits.for_book(conn, book.id)
    try:
        document = _open_epub(book) if any(r["status"] in edits.OPEN_STATUSES for r in rows) else None
    except (BookUnavailable, OSError) as err:
        return [ReviewItem(r, problem=str(err)) for r in rows]

    items = []
    for row in rows:
        if row["status"] not in edits.OPEN_STATUSES:
            items.append(ReviewItem(row))
            continue
        try:
            items.append(ReviewItem(row, preview=document.preview(edits.as_text_edit(row))))
        except EditNotApplicable as err:
            items.append(ReviewItem(row, problem=str(err)))
    return items


def apply_fixes(db: Database, library: CalibreLibrary, backups_dir: Path,
                book: Book, edit_ids: list[int], mark_failures: bool = True) -> ApplyOutcome:
    outcome = ApplyOutcome()
    with _apply_lock:
        with db.connect() as conn:
            rows = [r for r in edits.for_book(conn, book.id)
                    if r["id"] in edit_ids and r["status"] in edits.OPEN_STATUSES]
        document = _open_epub(book)
        notes = {}
        for row in rows:
            try:
                notes[row["id"]] = document.apply(edits.as_text_edit(row)).method
            except EditNotApplicable as err:
                outcome.failed[row["id"]] = str(err)

        if document.has_changes:
            _backup(book, backups_dir)
            document.save()
            library.record_file_change(book.id, "EPUB", book.epub)

        with db.connect() as conn:
            for edit_id, note in notes.items():
                edits.mark_applied(conn, edit_id, note)
                outcome.applied.append(edit_id)
            if mark_failures:
                for edit_id, error in outcome.failed.items():
                    edits.mark_failed(conn, edit_id, error)
    return outcome


def auto_apply(db: Database, library: CalibreLibrary, backups_dir: Path, edit_ids: list[int]) -> None:
    """Fixes that can't be applied stay pending, for review as usual"""
    with db.connect() as conn:
        by_book = edits.pending_by_book(conn, edit_ids)
    for book_id, ids in by_book.items():
        book = library.book(book_id)
        if book is None:
            continue
        # Never fail the sync: the fixes are stored and can still be reviewed
        try:
            outcome = apply_fixes(db, library, backups_dir, book, ids, mark_failures=False)
        except Exception:
            log.exception("Auto-apply failed for book %s", book_id)
            continue
        if outcome.applied:
            log.info("Auto-applied %d fix(es) to book %s", len(outcome.applied), book_id)


def _backup(book: Book, backups_dir: Path) -> Path:
    target_dir = backups_dir / str(book.id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{datetime.now():%Y%m%d-%H%M%S}.epub"
    shutil.copy2(book.epub, target)
    return target
