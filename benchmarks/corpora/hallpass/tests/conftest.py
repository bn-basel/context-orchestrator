"""Shared fixtures.

Tests run against a throwaway Postgres database (HALLPASS_TEST_DSN). Each test
gets a connection inside a transaction that is rolled back afterwards, so tests
never see each other's rows.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import psycopg
import pytest

from hallpass.core import clock

TEST_DSN = os.environ.get("HALLPASS_TEST_DSN", "postgresql://localhost/hallpass_test")


@pytest.fixture
def pg_conn():
    with psycopg.connect(TEST_DSN) as conn:
        conn.execute("BEGIN")
        try:
            yield conn
        finally:
            conn.rollback()


class FakeClock:
    """A clock that only moves when told to."""

    def __init__(self, start: datetime) -> None:
        self.current = start

    def now_utc(self) -> datetime:
        return self.current

    def advance(self, **delta) -> None:
        from datetime import timedelta

        self.current += timedelta(**delta)


@pytest.fixture
def frozen(monkeypatch):
    fake = FakeClock(datetime(2026, 3, 2, 9, 0, tzinfo=UTC))
    monkeypatch.setattr(clock, "now_utc", fake.now_utc)
    return fake
