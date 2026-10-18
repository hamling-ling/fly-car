"""Fixed-period deadline. A lag longer than the period drops the missed repeats."""

from __future__ import annotations

import time


class Next:
    """Fire on a period. ``tick`` is true once, then the deadline moves forward."""

    def __init__(self, period: float, *, start: float | None = None) -> None:
        self.period = float(period)
        self.at = time.monotonic() if start is None else float(start)

    def tick(self, now: float) -> bool:
        if now < self.at:
            return False
        self.at += self.period
        if self.at < now:
            self.at = now + self.period
        return True
