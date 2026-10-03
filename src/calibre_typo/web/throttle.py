from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class Throttle:
    """Per address only: a global limit would let anyone lock the admin out"""

    def __init__(self, per_client: int = 5, window_seconds: int = 15 * 60):
        self.per_client = per_client
        self.window = window_seconds
        self._by_client: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, failures: deque[float], now: float) -> None:
        while failures and now - failures[0] > self.window:
            failures.popleft()

    def allowed(self, client: str) -> bool:
        now = time.monotonic()
        with self._lock:
            mine = self._by_client[client]
            self._prune(mine, now)
            if not mine:
                del self._by_client[client]  # don't keep an entry for every visitor
            return len(mine) < self.per_client

    def failed(self, client: str) -> None:
        now = time.monotonic()
        with self._lock:
            self._by_client[client].append(now)

    def succeeded(self, client: str) -> None:
        with self._lock:
            self._by_client.pop(client, None)
