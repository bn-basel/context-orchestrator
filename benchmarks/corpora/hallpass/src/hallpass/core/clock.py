"""The one place that is allowed to ask what time it is.

Two styles exist in the codebase, both fine:

* module functions: ``clock.now_utc()`` (bookings, billing). Tests monkeypatch
  ``hallpass.core.clock.now_utc`` (and the name in the importing module).
* an injected ``Clock`` object (accounts, notifications), so tests can pass a
  FakeClock and ``advance()`` it.

New code: prefer taking a ``Clock`` parameter. Either way, never call
``datetime.now()`` directly.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Protocol

from hallpass.core import tz

_frozen: datetime | None = None


class Clock(Protocol):
    def now(self) -> datetime:
        """Current instant, timezone-aware UTC."""
        ...


class SystemClock:
    def now(self) -> datetime:
        return now_utc()

    def today_local(self) -> date:
        return tz.to_local(self.now()).date()


system_clock = SystemClock()


def now_utc() -> datetime:
    """Current instant, timezone-aware, in UTC."""
    if _frozen is not None:
        return _frozen
    return datetime.now(UTC)


# Older name, still used by worker.py and a few others.
now = now_utc


def today_local() -> date:
    """Today's date in Europe/London. Use this for 'is it tomorrow yet' logic."""
    return tz.to_local(now_utc()).date()


@contextmanager
def frozen(at: datetime) -> Iterator[None]:
    global _frozen
    if at.tzinfo is None:
        raise ValueError("freeze with an aware datetime")
    prev, _frozen = _frozen, at.astimezone(UTC)
    try:
        yield
    finally:
        _frozen = prev
