from __future__ import annotations

import re
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)

_BOOKS_SQL = """
    SELECT b.id, b.title, b.path, b.uuid,
           (SELECT group_concat(a.name, ' & ')
              FROM books_authors_link l JOIN authors a ON a.id = l.author
             WHERE l.book = b.id) AS authors
      FROM books b
"""


@dataclass(frozen=True)
class Book:
    id: int
    title: str
    authors: str
    uuid: str | None
    path: str
    formats: dict[str, Path] = field(default_factory=dict)

    @property
    def epub(self) -> Path | None:
        return self.formats.get("EPUB")


def _simplify(text: str | None) -> str:
    words = re.sub(r"[^\w\s]", "", (text or "").lower())
    return " ".join(words.split())


def suggest(books: list[Book], *, title: str | None, filename: str | None, limit: int = 3) -> list[Book]:
    # Words like "a" and "of" match nearly every book
    wanted = {w for w in _simplify(f"{title or ''} {Path(filename or '').stem}").split() if len(w) > 2}
    scored = [(len(wanted & set(_simplify(b.title).split())), b) for b in books]
    return [b for score, b in sorted(scored, key=lambda pair: -pair[0]) if score][:limit]


class LibraryUnavailable(Exception):
    pass


class CalibreLibrary:
    def __init__(self, root: Path):
        self.root = Path(root)

    @property
    def metadata_path(self) -> Path:
        return self.root / "metadata.db"

    def _connect(self, writable: bool = False) -> sqlite3.Connection:
        # Opening a missing file for writing would create it
        if not self.metadata_path.is_file():
            raise LibraryUnavailable(f"No Calibre library at {self.root} (metadata.db not found)")
        if writable:
            conn = sqlite3.connect(self.metadata_path, timeout=30)
        else:
            # as_uri() escapes "#", "?" and "%", which would end the path early
            conn = sqlite3.connect(f"{self.metadata_path.absolute().as_uri()}?mode=ro", uri=True, timeout=30)
        conn.row_factory = sqlite3.Row
        # Stand-ins for Calibre functions its triggers call
        conn.create_function("title_sort", 1, lambda title: title)
        conn.create_function("uuid4", 0, lambda: str(uuid.uuid4()))
        return conn

    def books(self) -> list[Book]:
        with closing(self._connect()) as conn:
            rows = conn.execute(_BOOKS_SQL + " ORDER BY b.title COLLATE NOCASE").fetchall()
        return [self._book(row) for row in rows]

    def book(self, book_id: int) -> Book | None:
        with closing(self._connect()) as conn:
            row = conn.execute(_BOOKS_SQL + " WHERE b.id = ?", (book_id,)).fetchone()
            if not row:
                return None
            formats = {
                f["format"]: self.root / row["path"] / f"{f['name']}.{f['format'].lower()}"
                for f in conn.execute("SELECT format, name FROM data WHERE book = ?", (book_id,))
            }
        return self._book(row, formats)

    @staticmethod
    def _book(row: sqlite3.Row, formats: dict[str, Path] | None = None) -> Book:
        return Book(row["id"], row["title"], row["authors"] or "", row["uuid"], row["path"], formats or {})

    def match(self, *, title: str | None, authors: str | None,
              identifiers: str | None, filename: str | None) -> int | None:
        """The ``calibre:<uuid>`` Calibre embeds is exact, titles are the fallback"""
        books = self.books()
        by_uuid = {b.uuid.lower(): b.id for b in books if b.uuid}
        for candidate in _UUID_RE.findall(identifiers or ""):
            if candidate.lower() in by_uuid:
                return by_uuid[candidate.lower()]

        filename_title = Path(filename or "").stem.split(" - ")[0]
        author_words = set(_simplify(authors).split())
        for wanted in (title, filename_title):
            key = _simplify(wanted)
            if not key:
                continue
            matches = [b for b in books if _simplify(b.title) == key]
            if len(matches) > 1 and author_words:
                matches = [b for b in matches if author_words & set(_simplify(b.authors).split())] or matches
            if len(matches) == 1:
                return matches[0].id
        return None

    def record_file_change(self, book_id: int, fmt: str, path: Path) -> None:
        """So Calibre-Web, OPDS clients and sync tools notice the change"""
        modified = datetime.now(timezone.utc).isoformat(sep=" ")
        with closing(self._connect(writable=True)) as conn, conn:
            conn.execute("UPDATE data SET uncompressed_size = ? WHERE book = ? AND format = ?",
                         (path.stat().st_size, book_id, fmt))
            conn.execute("UPDATE books SET last_modified = ? WHERE id = ?", (modified, book_id))
