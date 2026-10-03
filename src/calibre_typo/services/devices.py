"""Only token hashes are stored, so a database copy can't impersonate a device"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from dataclasses import dataclass

from ..db import now

# Crockford base32 (no I, L, O, U). 16 chars = 80 bits, safe without a rate limit
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_LOOKALIKES = str.maketrans("OIL", "011", "- \t")


@dataclass(frozen=True)
class Device:
    id: int
    name: str
    created_at: str
    last_seen_at: str | None
    plugin_version: str | None
    revoked_at: str | None

    @property
    def active(self) -> bool:
        return self.revoked_at is None


def _hash(token: str) -> str:
    # Case, dashes and look-alikes don't matter when typed
    return hashlib.sha256(token.upper().translate(_LOOKALIKES).encode()).hexdigest()


def _new_token() -> str:
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(16))
    return "-".join(raw[i:i + 4] for i in range(0, 16, 4))


def _device(row: sqlite3.Row) -> Device:
    return Device(row["id"], row["name"], row["created_at"], row["last_seen_at"],
                  row["plugin_version"], row["revoked_at"])


def list_devices(conn: sqlite3.Connection) -> list[Device]:
    rows = conn.execute("SELECT * FROM devices ORDER BY revoked_at IS NOT NULL, name COLLATE NOCASE")
    return [_device(r) for r in rows]


def get_device(conn: sqlite3.Connection, device_id: int) -> Device | None:
    row = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    return _device(row) if row else None


def create_device(conn: sqlite3.Connection, name: str) -> tuple[Device, str]:
    token = _new_token()
    cur = conn.execute("INSERT INTO devices (name, token_hash, created_at) VALUES (?, ?, ?)",
                       (name.strip() or "Reader", _hash(token), now()))
    return get_device(conn, cur.lastrowid), token


def reactivate(conn: sqlite3.Connection, device_id: int) -> str | None:
    """Active devices are refused, so a working token is never replaced by accident"""
    token = _new_token()
    cur = conn.execute("UPDATE devices SET token_hash = ?, revoked_at = NULL "
                       "WHERE id = ? AND revoked_at IS NOT NULL", (_hash(token), device_id))
    return token if cur.rowcount else None


def revoke(conn: sqlite3.Connection, device_id: int) -> None:
    conn.execute("UPDATE devices SET token_hash = NULL, revoked_at = ? WHERE id = ?", (now(), device_id))


def delete(conn: sqlite3.Connection, device_id: int) -> None:
    conn.execute("DELETE FROM devices WHERE id = ? AND revoked_at IS NOT NULL", (device_id,))


def authenticate(conn: sqlite3.Connection, token: str, plugin_version: str | None) -> Device | None:
    row = conn.execute("SELECT * FROM devices WHERE token_hash = ? AND revoked_at IS NULL",
                       (_hash(token),)).fetchone()
    if not row:
        return None
    conn.execute("UPDATE devices SET last_seen_at = ?, plugin_version = coalesce(?, plugin_version) WHERE id = ?",
                 (now(), plugin_version, row["id"]))
    return _device(row)
