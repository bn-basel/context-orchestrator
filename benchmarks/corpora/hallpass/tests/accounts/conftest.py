from datetime import UTC, datetime

import pytest

from hallpass.core import clock

# `pg_conn` comes from tests/conftest.py: throwaway DB, rolled back per test.

T0 = datetime(2025, 3, 12, 10, 0, tzinfo=UTC)


@pytest.fixture
def frozen():
    """Freeze hallpass.core.clock. Returns a function to move time."""
    state = {"cm": clock.frozen(T0)}
    state["cm"].__enter__()

    def move_to(at: datetime) -> None:
        state["cm"].__exit__(None, None, None)
        state["cm"] = clock.frozen(at)
        state["cm"].__enter__()

    yield move_to
    state["cm"].__exit__(None, None, None)


@pytest.fixture
def make_resident(pg_conn):
    def _make(email="sam@example.org", name="Sam Okafor", phone=None, last_login_at=None):
        (rid,) = pg_conn.execute(
            "INSERT INTO residents (email, full_name, phone, created_at, last_login_at) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (email, name, phone, T0, last_login_at),
        ).fetchone()
        return rid

    return _make


@pytest.fixture
def make_staff(pg_conn):
    def _make(email="duty.manager@council.example", role="facility_staff", active=True):
        (sid,) = pg_conn.execute(
            "INSERT INTO staff_users (email, full_name, role, active) VALUES (%s, 'Test Staff', %s, %s) "
            "RETURNING id",
            (email, role, active),
        ).fetchone()
        return sid

    return _make
