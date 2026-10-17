"""Simple in-process login throttle (per username+IP). Resets on API restart; documented limitation."""

from __future__ import annotations

import time
from collections import defaultdict


class LoginThrottle:
    def __init__(self, max_failures: int, lockout_seconds: int, clock=time.monotonic) -> None:  # noqa: ANN001
        self.max, self.lock, self.clock = max_failures, lockout_seconds, clock
        self._fails: dict[str, list[float]] = defaultdict(list)

    def _prune(self, key: str) -> list[float]:
        now = self.clock()
        self._fails[key] = [t for t in self._fails[key] if now - t < self.lock]
        return self._fails[key]

    def blocked(self, key: str) -> bool:
        return len(self._prune(key)) >= self.max

    def fail(self, key: str) -> None:
        self._prune(key).append(self.clock())

    def success(self, key: str) -> None:
        self._fails.pop(key, None)
