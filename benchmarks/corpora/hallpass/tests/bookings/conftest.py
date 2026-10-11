from __future__ import annotations

from datetime import UTC, datetime, time

import pytest

# `pg_conn` comes from the top-level tests/conftest.py: a connection to the
# throwaway test database inside a transaction that's rolled back afterwards.

_BOOKINGS_MODULES = (
    "hallpass.bookings.availability",
    "hallpass.bookings.lifecycle",
    "hallpass.bookings.recurring",
    "hallpass.bookings.waitlist",
    "hallpass.bookings.blackouts",
    "hallpass.bookings.jobs",
)


@pytest.fixture
def frozen_now(monkeypatch):
    """Pin the clock. Usage: ``frozen_now(datetime(..., tzinfo=UTC))``.

    Patches hallpass.core.clock.now_utc *and* the name in each bookings module,
    because they all do ``from hallpass.core.clock import now_utc``.
    """
    state = {"now": datetime(2025, 9, 1, 9, 0, tzinfo=UTC)}

    def _now():
        return state["now"]

    monkeypatch.setattr("hallpass.core.clock.now_utc", _now)
    for mod in _BOOKINGS_MODULES:
        monkeypatch.setattr(f"{mod}.now_utc", _now, raising=False)

    def set_now(dt: datetime) -> None:
        assert dt.tzinfo is not None
        state["now"] = dt

    return set_now


@pytest.fixture
def sent(monkeypatch):
    """Capture outbox messages instead of writing notifications_outbox rows.
    Each item is (template, first ref) -- e.g. ("booking_confirmed", 123)."""
    out: list[tuple] = []

    def fake_enqueue(conn, *, template, **refs):
        out.append((template, next(iter(refs.values()), None)))
        return []

    for mod in _BOOKINGS_MODULES:
        monkeypatch.setattr(f"{mod}.enqueue", fake_enqueue, raising=False)
    return out


@pytest.fixture
def flat_price(monkeypatch):
    """Every hour costs £20. Pricing has its own tests; we don't care here."""

    class _Quote:
        def __init__(self, pence):
            self.total_pence = pence
            self.gross_pence = pence

    def fake_quote(conn, *, space_id, starts_at, ends_at, resident_id, organisation_id, series_occurrences=1):
        minutes = int((ends_at - starts_at).total_seconds() // 60)
        return _Quote(minutes * 2000 // 60)

    monkeypatch.setattr("hallpass.bookings.lifecycle.quote_price", fake_quote)
    monkeypatch.setattr("hallpass.billing.pricing.quote_price", fake_quote)
    return fake_quote


@pytest.fixture
def refunds(monkeypatch):
    calls: list[tuple[int, bool]] = []

    def fake(conn, *, booking, full_refund=False):
        calls.append((booking.id, full_refund))
        return None

    monkeypatch.setattr("hallpass.billing.refunds.refund_requested", fake)
    return calls


@pytest.fixture
def env(frozen_now, sent, flat_price, refunds):
    """The usual bundle for DB tests."""
    return {"set_now": frozen_now, "sent": sent, "refunds": refunds}


@pytest.fixture
def hall(pg_conn):
    """A facility with one sports hall open 08:00-22:00 every day."""
    with pg_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO facilities (name, address_line1, postcode) VALUES ('Test Leisure Centre', '1 High St', 'TE1 1ST') RETURNING id"
        )
        (facility_id,) = cur.fetchone()
        cur.execute(
            "INSERT INTO spaces (facility_id, name, kind, is_bookable, sort_order) VALUES (%s, 'Hall A', 'sports_hall', true, 1) RETURNING id",
            (facility_id,),
        )
        (space_id,) = cur.fetchone()
        for wd in range(1, 8):
            cur.execute(
                "INSERT INTO opening_hours (space_id, weekday, opens_at, closes_at) VALUES (%s, %s, %s, %s)",
                (space_id, wd, time(8, 0), time(22, 0)),
            )
    return {"facility_id": facility_id, "space_id": space_id}


def _resident(pg_conn, email, name, postcode):
    with pg_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO residents (email, display_name, postcode) VALUES (%s, %s, %s) RETURNING id",
            (email, name, postcode),
        )
        return cur.fetchone()[0]


@pytest.fixture
def resident(pg_conn):
    return _resident(pg_conn, "sam@example.org", "Sam Hirer", "TE1 2AB")


@pytest.fixture
def second_resident(pg_conn):
    return _resident(pg_conn, "alex@example.org", "Alex W", "TE1 3CD")


@pytest.fixture
def club(pg_conn, resident):
    """Thornbury Badminton Club, on account, with `resident` as its admin."""
    with pg_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO organisations (name, kind, on_account, invoice_email) "
            "VALUES ('Thornbury Badminton Club', 'club', true, 'treasurer@thornburybc.example') RETURNING id"
        )
        (org_id,) = cur.fetchone()
        cur.execute(
            "INSERT INTO organisation_members (organisation_id, resident_id, role) VALUES (%s, %s, 'admin')",
            (org_id, resident),
        )
    return org_id
