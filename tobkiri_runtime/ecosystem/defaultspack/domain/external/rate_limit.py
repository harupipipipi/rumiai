from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, Deque[float]] = defaultdict(deque)

    def allow(self, key: str, limit: int, window_seconds: int = 60) -> bool:
        if limit <= 0:
            return True
        now = time.time()
        bucket = self._hits[key]
        while bucket and now - bucket[0] >= window_seconds:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True

    def clear(self) -> None:
        self._hits.clear()


GLOBAL_RATE_LIMITER = SlidingWindowRateLimiter()
