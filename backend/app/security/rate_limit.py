"""In-process sliding-window rate limiter.

Good for a single API process (the default deployment). For multi-instance
deployments swap this for a Redis-backed implementation with the same
interface.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from app.core.errors import RateLimitedError


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, window_seconds: float = 60.0) -> None:
        if limit <= 0:
            return
        now = time.monotonic()
        q = self._hits[key]
        while q and now - q[0] > window_seconds:
            q.popleft()
        if len(q) >= limit:
            retry = max(1, int(window_seconds - (now - q[0])))
            raise RateLimitedError(
                "You're sending requests too quickly.",
                reason=f"Limit is {limit} requests per {int(window_seconds)}s.",
                next_step=f"Wait about {retry}s and try again.",
            )
        q.append(now)
        if len(self._hits) > 10000:  # bound memory
            for k in list(self._hits)[:1000]:
                if not self._hits[k]:
                    del self._hits[k]

    def reset(self) -> None:
        self._hits.clear()


rate_limiter = RateLimiter()
