"""In-process rate limiting.

This is a deliberately small implementation for a single-instance MVP. It is
thread-safe (sync FastAPI endpoints run in a thread pool) and covers abuse of
the sensitive write endpoints. In a multi-instance deployment the limiter must
be replaced by a shared store (for example Redis) or enforced at the reverse
proxy; this limitation is documented in the README.
"""

from __future__ import annotations

import threading
import time
from collections import deque


class RateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = {}
        self._checks = 0

    def hit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        """Register a hit.

        Returns `(allowed, retry_after_seconds)`. A limit lower than or equal to
        zero disables the limiter for the key.
        """

        if limit <= 0:
            return True, 0

        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            self._checks += 1
            if self._checks % 1000 == 0:
                self._prune(cutoff)
            bucket = self._hits.setdefault(key, deque())
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(1, int(window_seconds - (now - bucket[0])) + 1)
                return False, retry_after
            bucket.append(now)
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
            self._checks = 0

    def _prune(self, cutoff: float) -> None:
        stale = [key for key, bucket in self._hits.items() if not bucket or bucket[-1] <= cutoff]
        for key in stale:
            self._hits.pop(key, None)
