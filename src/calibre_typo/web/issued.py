from __future__ import annotations

import secrets
import threading
import time


class IssuedTokens:
    """Keeps tokens out of the session cookie, which is signed but readable"""

    def __init__(self, ttl_seconds: int = 30 * 60):
        self.ttl = ttl_seconds
        self._entries: dict[str, tuple[int, str, float]] = {}
        self._lock = threading.Lock()

    def remember(self, device_id: int, token: str) -> str:
        ticket = secrets.token_urlsafe(16)
        now = time.monotonic()
        with self._lock:
            self._entries = {k: v for k, v in self._entries.items() if v[2] > now}
            self._entries[ticket] = (device_id, token, now + self.ttl)
        return ticket

    def get(self, ticket: str | None, device_id: int) -> str | None:
        with self._lock:
            entry = self._entries.get(ticket or "")
        if entry and entry[0] == device_id and entry[2] > time.monotonic():
            return entry[1]
        return None
