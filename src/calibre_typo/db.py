from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

# Append only: PRAGMA user_version counts applied entries
MIGRATIONS: list[str] = [
    """
    CREATE TABLE settings (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );

    CREATE TABLE devices (
        id             INTEGER PRIMARY KEY,
        name           TEXT NOT NULL,
        token_hash     TEXT UNIQUE,
        created_at     TEXT NOT NULL,
        last_seen_at   TEXT,
        plugin_version TEXT,
        revoked_at     TEXT
    );

    CREATE TABLE edits (
        id          INTEGER PRIMARY KEY,
        uid         TEXT UNIQUE NOT NULL,
        device_id   INTEGER REFERENCES devices(id) ON DELETE SET NULL,
        created_at  TEXT,
        received_at TEXT NOT NULL,
        status      TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'applied', 'rejected', 'failed')),
        book_id     INTEGER,
        book_title  TEXT,
        book_authors TEXT,
        identifiers TEXT,
        filename    TEXT,
        xpointer    TEXT,
        original    TEXT NOT NULL,
        replacement TEXT NOT NULL,
        ctx_before  TEXT NOT NULL DEFAULT '',
        ctx_after   TEXT NOT NULL DEFAULT '',
        match_note  TEXT,
        error       TEXT,
        applied_at  TEXT
    );

    CREATE INDEX edits_by_book ON edits(book_id, status);
    """,
    """
    CREATE TABLE sessions (
        id_hash    TEXT PRIMARY KEY,
        created_at INTEGER NOT NULL
    );
    """,
]


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def migrate(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            for number, script in enumerate(MIGRATIONS[version:], start=version + 1):
                conn.executescript(script)
                conn.execute(f"PRAGMA user_version = {number}")


def get_setting(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
