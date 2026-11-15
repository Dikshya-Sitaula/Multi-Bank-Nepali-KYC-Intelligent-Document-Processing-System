"""In-memory sliding-window rate limiter for the login endpoint.

WHY: limits password guessing. It is per process, which is enough for this single-server
project; a multi-server deployment would move this to Redis or the reverse proxy
(documented in docs/PRIVACY.md).
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self, max_attempts: int, window_s: float) -> None:
        self.max_attempts = max_attempts
        self.window_s = window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str) -> tuple[bool, float]:
        """Record an attempt. Returns (allowed, retry_after_seconds)."""
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.window_s:
                q.popleft()
            if len(q) >= self.max_attempts:
                return False, max(0.0, self.window_s - (now - q[0]))
            q.append(now)
            return True, 0.0

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)
