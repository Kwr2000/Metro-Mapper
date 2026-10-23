"""Hard call budgets for live sources. Fails closed.

Spend is derived from the run log (live runs only), so the budget survives
restarts and is the same number the health page shows. Limits live in
config/budgets.yaml. Windows use UTC calendar days and months. An adapter with
no budget entry may not run live at all.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import config, runlog


class BudgetExceeded(RuntimeError):
    pass


def _day_start(now: datetime) -> datetime:
    return now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def _month_start(now: datetime) -> datetime:
    return _day_start(now).replace(day=1)


def spent(adapter: str, now: datetime | None = None) -> tuple[int, int]:
    """(calls today, calls this month) from the run log."""
    now = now or runlog.utcnow()
    runs = runlog.read_all()
    return (
        runlog.live_calls_since(adapter, _day_start(now), runs),
        runlog.live_calls_since(adapter, _month_start(now), runs),
    )


@dataclass
class CallBudget:
    """Per-run budget guard. `remaining` is fixed when the run starts."""

    adapter: str
    per_day: int | None
    per_month: int | None
    min_interval_seconds: float
    remaining: int | None
    max_minutes: float | None = None
    used: int = 0
    _last_call: float | None = field(default=None, repr=False)
    _started: float = field(default_factory=time.monotonic, repr=False)

    def out_of_time(self) -> bool:
        return self.max_minutes is not None and time.monotonic() - self._started > self.max_minutes * 60

    def elapsed(self) -> float:
        return time.monotonic() - self._started

    @classmethod
    def for_adapter(cls, adapter: str, now: datetime | None = None) -> "CallBudget":
        b = config.budgets().adapters.get(adapter)
        if b is None:
            # No budget line: no live calls (fails closed). Fixture runs are unaffected.
            return cls(adapter, 0, 0, 0.0, 0)
        today, month = spent(adapter, now)
        limits = []
        if b.per_day is not None:
            limits.append(b.per_day - today)
        if b.per_month is not None:
            limits.append(b.per_month - month)
        remaining = max(0, min(limits)) if limits else None
        return cls(adapter, b.per_day, b.per_month, b.min_interval_seconds, remaining, b.max_minutes)

    def allows(self, n: int = 1) -> bool:
        return self.remaining is None or self.used + n <= self.remaining

    def spend(self, sleep: bool = True) -> None:
        """Call immediately before each live request."""
        if not self.allows(1):
            raise BudgetExceeded(
                f"{self.adapter}: call budget exhausted "
                f"(per_day={self.per_day}, per_month={self.per_month})"
            )
        if sleep and self.min_interval_seconds and self._last_call is not None:
            wait = self.min_interval_seconds - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
        self._last_call = time.monotonic()
        self.used += 1
