from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, date, datetime, time

import pytest

from hallpass.billing.pricing import PriceRule
from hallpass.core.tz import LONDON

WEEKDAYS = 0b0011111
WEEKEND = 0b1100000
EVERY_DAY = 0b1111111


def utc(y: int, mo: int, d: int, h: int = 0, mi: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


def london(y: int, mo: int, d: int, h: int = 0, mi: int = 0) -> datetime:
    """Local wall-clock time converted to UTC (what the DB holds)."""
    return datetime(y, mo, d, h, mi, tzinfo=LONDON).astimezone(UTC)


def make_rule(
    id: int = 1,
    *,
    start: time = time(9, 0),
    end: time = time(17, 0),
    rate: int = 3000,
    days: int = EVERY_DAY,
    valid_from: date = date(2023, 4, 1),
    valid_to: date | None = None,
    hirer_type: str = "resident",
    space_id: int | None = 10,
    priority: int = 0,
) -> PriceRule:
    return PriceRule(
        id=id,
        space_id=space_id,
        space_kind=None if space_id is not None else "sports_hall",
        hirer_type=hirer_type,
        weekday_mask=days,
        local_from=start,
        local_to=end,
        pence_per_hour=rate,
        valid_from=valid_from,
        valid_to=valid_to,
        priority=priority,
    )


@pytest.fixture
def sports_hall_rules() -> list[PriceRule]:
    """Roughly the 2025/26 tariff for the Northfield sports hall, resident rates."""
    return [
        make_rule(1, start=time(7, 0), end=time(17, 0), rate=3600, days=WEEKDAYS),
        make_rule(2, start=time(17, 0), end=time(22, 0), rate=4800, days=WEEKDAYS),  # "peak"
        make_rule(3, start=time(8, 0), end=time(20, 0), rate=4200, days=WEEKEND),
    ]


class FakeCursor:
    def __init__(self, conn: FakeConn):
        self.conn = conn
        self._result: list = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.conn.statements.append((" ".join(sql.split()), params))
        self._result = self.conn.responses.pop(0) if self.conn.responses else []
        return self

    def fetchone(self):
        return self._result[0] if self._result else None

    def fetchall(self):
        return list(self._result)


class FakeConn:
    """Records SQL and returns canned rows in order. Good enough for the
    webhook tests; anything that needs real constraints is in tests/db/."""

    def __init__(self, responses: list[list] | None = None):
        self.responses = list(responses or [])
        self.statements: list[tuple[str, object]] = []

    def cursor(self, row_factory=None):
        return FakeCursor(self)

    def execute(self, sql, params=None):
        return FakeCursor(self).execute(sql, params)

    @contextmanager
    def transaction(self):
        # Real psycopg would make a savepoint. We just note it happened.
        self.statements.append(("SAVEPOINT", None))
        yield self


@pytest.fixture
def fake_conn() -> FakeConn:
    return FakeConn()
