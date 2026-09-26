"""In-process sliding-window rate limiting for POST /bot/message.

Every bot message can cost an LLM call, and a public channel (a website
widget) is reachable by anyone -- so bursts are capped per customer and per
tenant before any work is done. Limits come from project_config.yaml
(`bot.rate_limit`).

State lives in this process's memory: exact for a single backend instance.
With N instances each enforces its own window (effective limit up to N x);
move this to Redis/Postgres if the backend is ever scaled out.
"""

import time
from collections import deque
from collections.abc import Callable, Hashable

from common import PROJECT_CONFIG

_rate_config = PROJECT_CONFIG.get("bot", {}).get("rate_limit", {})
PER_USER_PER_MINUTE = _rate_config.get("per_user_per_minute", 20)
PER_TENANT_PER_MINUTE = _rate_config.get("per_tenant_per_minute", 300)

# above this many tracked keys, idle ones are swept so memory stays bounded
_SWEEP_THRESHOLD = 10_000


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: float = 60.0, clock: Callable[[], float] = time.monotonic) -> None:
        self.limit = limit
        self.window = window_seconds
        self.clock = clock
        self._hits: dict[Hashable, deque[float]] = {}

    def hit(self, key: Hashable) -> float | None:
        """Record one request for `key`. Returns None when allowed, or the
        seconds until the next request would be allowed when over the limit
        (a rejected request is not counted)."""
        now = self.clock()
        if len(self._hits) > _SWEEP_THRESHOLD:
            self._sweep(now)

        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return hits[0] + self.window - now
        hits.append(now)
        return None

    def reset(self) -> None:
        self._hits.clear()

    def _sweep(self, now: float) -> None:
        for key in [k for k, hits in self._hits.items() if not hits or hits[-1] <= now - self.window]:
            del self._hits[key]


per_user = SlidingWindowLimiter(PER_USER_PER_MINUTE)
per_tenant = SlidingWindowLimiter(PER_TENANT_PER_MINUTE)
