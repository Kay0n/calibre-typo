from __future__ import annotations

import hashlib
import secrets
import sqlite3
import time

from werkzeug.security import check_password_hash, generate_password_hash

from ..db import get_setting, set_setting

_PASSWORD_KEY = "admin_password_hash"
_SECRET_KEY = "session_secret"
SESSION_DAYS = 30


def is_set_up(conn: sqlite3.Connection) -> bool:
    return get_setting(conn, _PASSWORD_KEY) is not None


# Empty password = login off (for sign-in proxies), stored as "" rather than hashed
def _stored(password: str) -> str:
    return generate_password_hash(password) if password else ""


def login_disabled(conn: sqlite3.Connection) -> bool:
    return get_setting(conn, _PASSWORD_KEY) == ""


def set_password(conn: sqlite3.Connection, password: str) -> None:
    set_setting(conn, _PASSWORD_KEY, _stored(password))
    end_all_sessions(conn)


def claim(conn: sqlite3.Connection, password: str) -> bool:
    """INSERT OR IGNORE, so simultaneous setups can't overwrite each other"""
    cur = conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                       (_PASSWORD_KEY, _stored(password)))
    return cur.rowcount == 1


def verify_password(conn: sqlite3.Connection, password: str) -> bool:
    stored = get_setting(conn, _PASSWORD_KEY)
    if stored == "":
        return password == ""
    return bool(stored) and check_password_hash(stored, password)


# Server-side, so logout also ends copied cookies. Hashes only
def _hash(session_id: str) -> str:
    return hashlib.sha256(session_id.encode()).hexdigest()


def start_session(conn: sqlite3.Connection) -> str:
    now = int(time.time())
    conn.execute("DELETE FROM sessions WHERE created_at < ?", (now - SESSION_DAYS * 86400,))
    session_id = secrets.token_urlsafe(32)
    conn.execute("INSERT INTO sessions (id_hash, created_at) VALUES (?, ?)", (_hash(session_id), now))
    return session_id


def session_valid(conn: sqlite3.Connection, session_id: str) -> bool:
    oldest = int(time.time()) - SESSION_DAYS * 86400
    row = conn.execute("SELECT 1 FROM sessions WHERE id_hash = ? AND created_at >= ?",
                       (_hash(session_id), oldest)).fetchone()
    return row is not None


def end_session(conn: sqlite3.Connection, session_id: str) -> None:
    conn.execute("DELETE FROM sessions WHERE id_hash = ?", (_hash(session_id),))


def end_all_sessions(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM sessions")


def session_secret(conn: sqlite3.Connection) -> str:
    """Stored, so sessions survive restarts"""
    secret = get_setting(conn, _SECRET_KEY)
    if not secret:
        secret = secrets.token_hex(32)
        set_setting(conn, _SECRET_KEY, secret)
    return secret
