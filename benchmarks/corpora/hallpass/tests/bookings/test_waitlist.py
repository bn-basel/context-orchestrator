import threading
from datetime import UTC, datetime, timedelta

import pytest

from hallpass.bookings import jobs, lifecycle, waitlist
from hallpass.core.errors import ValidationError

pytestmark = pytest.mark.db

S = datetime(2025, 9, 10, 17, 0, tzinfo=UTC)
E = datetime(2025, 9, 10, 18, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _env(env):
    env["set_now"](datetime(2025, 9, 1, 9, 0, tzinfo=UTC))


@pytest.fixture
def taken(pg_conn, hall, resident):
    b = lifecycle.place_hold(pg_conn, space_id=hall["space_id"], starts_at=S, ends_at=E, resident_id=resident)
    lifecycle.confirm(pg_conn, b.id)
    return b


def _entry(pg_conn, entry_id):
    with pg_conn.cursor() as cur:
        cur.execute("SELECT status, offer_booking_id FROM waitlist_entries WHERE id = %s", (entry_id,))
        return cur.fetchone()


def test_join_is_idempotent(pg_conn, hall, resident):
    a = waitlist.join(pg_conn, resident_id=resident, space_id=hall["space_id"], starts_at=S, ends_at=E)
    b = waitlist.join(pg_conn, resident_id=resident, space_id=hall["space_id"], starts_at=S, ends_at=E)
    assert a == b


def test_join_limit(pg_conn, hall, resident):
    for i in range(waitlist.MAX_ENTRIES_PER_RESIDENT):
        waitlist.join(
            pg_conn,
            resident_id=resident,
            space_id=hall["space_id"],
            starts_at=S + timedelta(days=i),
            ends_at=E + timedelta(days=i),
        )
    with pytest.raises(ValidationError):
        waitlist.join(
            pg_conn, resident_id=resident, space_id=hall["space_id"], starts_at=S + timedelta(days=9), ends_at=E + timedelta(days=9)
        )


def test_cannot_wait_for_the_past(pg_conn, hall, resident, frozen_now):
    frozen_now(S + timedelta(minutes=1))
    with pytest.raises(ValidationError):
        waitlist.join(pg_conn, resident_id=resident, space_id=hall["space_id"], starts_at=S, ends_at=E)


def test_cancellation_offers_to_first_in_queue(pg_conn, hall, second_resident, taken, sent):
    entry_id = waitlist.join(pg_conn, resident_id=second_resident, space_id=hall["space_id"], starts_at=S, ends_at=E)

    lifecycle.cancel(pg_conn, taken.id, reason=lifecycle.CUSTOMER)

    status, offer_booking_id = _entry(pg_conn, entry_id)
    with pg_conn.cursor() as cur:
        cur.execute("SELECT status, resident_id, hold_expires_at FROM bookings WHERE id = %s", (offer_booking_id,))
        b_status, b_res, expires = cur.fetchone()
    assert status == "offered"
    assert (b_status, b_res) == ("held", second_resident)
    assert expires == datetime(2025, 9, 1, 11, 0, tzinfo=UTC)  # OFFER_TTL, not the normal hold
    assert ("waitlist_offer", entry_id) in sent


def test_paying_for_offer_closes_entry(pg_conn, hall, second_resident, taken):
    entry_id = waitlist.join(pg_conn, resident_id=second_resident, space_id=hall["space_id"], starts_at=S, ends_at=E)
    lifecycle.cancel(pg_conn, taken.id, reason=lifecycle.CUSTOMER)
    _, offer_booking_id = _entry(pg_conn, entry_id)
    lifecycle.confirm(pg_conn, offer_booking_id)
    assert _entry(pg_conn, entry_id)[0] == "accepted"


def test_lapsed_offer_goes_to_next_person(pg_conn, hall, resident, second_resident, taken, frozen_now, flags_on):
    first = waitlist.join(pg_conn, resident_id=second_resident, space_id=hall["space_id"], starts_at=S, ends_at=E)
    lifecycle.cancel(pg_conn, taken.id, reason=lifecycle.CUSTOMER)
    # original hirer changes their mind and queues up behind
    second = waitlist.join(pg_conn, resident_id=resident, space_id=hall["space_id"], starts_at=S, ends_at=E)

    frozen_now(datetime(2025, 9, 1, 11, 5, tzinfo=UTC))
    jobs.release_expired_holds(pg_conn)
    assert jobs.sweep_waitlist(pg_conn) == 1
    assert _entry(pg_conn, first)[0] == "lapsed"
    assert _entry(pg_conn, second)[0] == "offered"


def test_waiting_for_longer_range_not_offered_shorter(pg_conn, hall, second_resident, taken):
    waitlist.join(
        pg_conn, resident_id=second_resident, space_id=hall["space_id"], starts_at=S, ends_at=E + timedelta(hours=1)
    )
    lifecycle.cancel(pg_conn, taken.id, reason=lifecycle.CUSTOMER, promote_waitlist=False)
    assert waitlist.promote_for_slot(pg_conn, hall["space_id"], S, E) is None


def test_no_offer_inside_min_notice(pg_conn, hall, frozen_now):
    frozen_now(S - timedelta(hours=1))
    assert waitlist.promote_for_slot(pg_conn, hall["space_id"], S, E) is None


@pytest.fixture
def flags_on(monkeypatch):
    monkeypatch.setattr("hallpass.core.flags.is_enabled", lambda key, **kw: True)


@pytest.mark.skip(reason="HP-541 reproduction; needs two real connections, run by hand with --run-race")
def test_concurrent_promotion(pg_dsn, hall, resident, second_resident):
    """Two promoters for the same freed slot. Expected (once fixed): exactly
    one waitlist_offer row in the outbox, and the first entry 'offered'.
    Today: usually three offer rows (two to the first person, one to the
    second) and the first entry back at 'waiting'."""
    import psycopg

    barrier = threading.Barrier(2)

    def run():
        with psycopg.connect(pg_dsn) as conn:
            barrier.wait()
            waitlist.promote_for_slot(conn, hall["space_id"], S, E)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    with psycopg.connect(pg_dsn) as conn:
        (offers,) = conn.execute(
            "SELECT count(*) FROM notifications_outbox WHERE kind = 'waitlist_offer' AND channel = 'email'"
        ).fetchone()
    assert offers == 1
