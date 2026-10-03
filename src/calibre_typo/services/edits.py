from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from ..db import now
from ..epub import TextEdit
from ..library import Book, CalibreLibrary

OPEN_STATUSES = ("pending", "failed")


@dataclass(frozen=True)
class BookSummary:
    book_id: int | None
    title: str
    authors: str
    pending: int
    failed: int
    applied: int
    last_received: str


def as_text_edit(row: Mapping[str, Any]) -> TextEdit:
    return TextEdit(original=row["original"], replacement=row["replacement"],
                    before=row["ctx_before"] or "", after=row["ctx_after"] or "",
                    xpointer=row["xpointer"])


def _text(item: Mapping[str, Any], key: str) -> str | None:
    value = item.get(key)
    return value if isinstance(value, str) else None


def receive(conn: sqlite3.Connection, library: CalibreLibrary, device_id: int,
            submitted: Iterable[Mapping[str, Any]]) -> list[str]:
    """Re-sent uids are acknowledged, not duplicated, so devices can retry. Bad fields
    are dropped, as failing the request would block the device's queue"""
    accepted = []
    for item in submitted:
        uid = (_text(item, "uid") or "").strip()
        original, replacement = _text(item, "original"), _text(item, "replacement")
        if not uid or not original or replacement is None:
            continue
        if conn.execute("SELECT 1 FROM edits WHERE uid = ?", (uid,)).fetchone() is None:
            title, authors = _text(item, "title"), _text(item, "authors")
            identifiers, filename = _text(item, "identifiers"), _text(item, "filename")
            book_id = library.match(title=title, authors=authors, identifiers=identifiers, filename=filename)
            conn.execute(
                """INSERT INTO edits (uid, device_id, created_at, received_at, book_id, book_title,
                       book_authors, identifiers, filename, xpointer, original, replacement,
                       ctx_before, ctx_after)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (uid, device_id, _text(item, "created_at"), now(), book_id, title, authors,
                 identifiers, filename, _text(item, "xpointer"), original, replacement,
                 _text(item, "context_before") or "", _text(item, "context_after") or ""),
            )
        accepted.append(uid)
    return accepted


def release_missing_books(conn: sqlite3.Connection, book_ids: set[int]) -> None:
    """Otherwise fixes for books removed from the library would be stuck"""
    rows = conn.execute("SELECT DISTINCT book_id FROM edits WHERE book_id IS NOT NULL AND status IN (?, ?)",
                        OPEN_STATUSES)
    gone = [r["book_id"] for r in rows if r["book_id"] not in book_ids]
    conn.executemany("UPDATE edits SET book_id = NULL WHERE book_id = ? AND status IN (?, ?)",
                     [(book_id, *OPEN_STATUSES) for book_id in gone])


def book_summaries(conn: sqlite3.Connection, books: list[Book]) -> list[BookSummary]:
    rows = conn.execute("""
        SELECT book_id, sum(status = 'pending') AS pending, sum(status = 'failed') AS failed,
               sum(status = 'applied') AS applied, max(received_at) AS last_received
          FROM edits WHERE book_id IS NOT NULL
         GROUP BY book_id
         ORDER BY sum(status IN ('pending', 'failed')) > 0 DESC, last_received DESC
    """).fetchall()
    by_id = {b.id: b for b in books}
    summaries = []
    for r in rows:
        if book := by_id.get(r["book_id"]):  # history of deleted books isn't worth showing
            summaries.append(BookSummary(r["book_id"], book.title, book.authors,
                                         r["pending"], r["failed"], r["applied"], r["last_received"]))
    return summaries


def for_book(conn: sqlite3.Connection, book_id: int) -> list[sqlite3.Row]:
    return conn.execute("""
        SELECT e.*, d.name AS device_name FROM edits e LEFT JOIN devices d ON d.id = e.device_id
         WHERE e.book_id = ?
         ORDER BY e.status IN ('applied', 'rejected'), e.id
    """, (book_id,)).fetchall()


def unmatched(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM edits WHERE book_id IS NULL ORDER BY id").fetchall()


def unmatched_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT count(*) FROM edits WHERE book_id IS NULL").fetchone()[0]


def assign_book(conn: sqlite3.Connection, edit_id: int, book_id: int) -> None:
    conn.execute("UPDATE edits SET book_id = ? WHERE id = ? AND book_id IS NULL", (book_id, edit_id))


def discard_unmatched(conn: sqlite3.Connection, edit_id: int) -> None:
    conn.execute("DELETE FROM edits WHERE id = ? AND book_id IS NULL", (edit_id,))


def set_replacement(conn: sqlite3.Connection, book_id: int, edit_id: int, replacement: str) -> None:
    conn.execute("UPDATE edits SET replacement = ? WHERE id = ? AND book_id = ? AND status IN (?, ?)",
                 (replacement, edit_id, book_id, *OPEN_STATUSES))


def reject(conn: sqlite3.Connection, book_id: int, edit_ids: Iterable[int]) -> None:
    conn.executemany("UPDATE edits SET status = 'rejected' WHERE id = ? AND book_id = ?",
                     [(i, book_id) for i in edit_ids])


def reopen(conn: sqlite3.Connection, book_id: int, edit_id: int) -> None:
    conn.execute("UPDATE edits SET status = 'pending', error = NULL "
                 "WHERE id = ? AND book_id = ? AND status = 'rejected'", (edit_id, book_id))


def mark_applied(conn: sqlite3.Connection, edit_id: int, match_note: str) -> None:
    conn.execute("UPDATE edits SET status = 'applied', error = NULL, match_note = ?, applied_at = ? "
                 "WHERE id = ?", (match_note, now(), edit_id))


def mark_failed(conn: sqlite3.Connection, edit_id: int, error: str) -> None:
    conn.execute("UPDATE edits SET status = 'failed', error = ? WHERE id = ?", (error, edit_id))
