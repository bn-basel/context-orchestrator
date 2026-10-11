from datetime import UTC, datetime, timedelta

import pytest

from hallpass.bookings import jobs, lifecycle
from hallpass.bookings.models import BookingConflict, BookingStatus, HoldExpired, IllegalTransition
from hallpass.core.errors import NotFound

pytestmark = pytest.mark.db

# 18:00-19:00 BST on a Wednesday
S = datetime(2025, 9, 10, 17, 0, tzinfo=UTC)
E = datetime(2025, 9, 10, 18, 0, tzinfo=UTC)


@pytest.fixture
def held(pg_conn, hall, resident, env):
    env["set_now"](datetime(2025, 9, 1, 9, 0, tzinfo=UTC))
    return lifecycle.place_hold(pg_conn, space_id=hall["space_id"], starts_at=S, ends_at=E, resident_id=resident)


def test_hold_sets_expiry(held):
    assert held.status == BookingStatus.HELD
    assert held.hold_expires_at == datetime(2025, 9, 1, 9, 15, tzinfo=UTC)  # default HALLPASS_HOLD_MINUTES
    assert held.price_pence == 2000


def test_second_hold_on_same_slot_conflicts(pg_conn, hall, resident, held):
    with pytest.raises(BookingConflict):
        lifecycle.place_hold(pg_conn, space_id=hall["space_id"], starts_at=S, ends_at=E, resident_id=resident)


def test_partial_overlap_conflicts(pg_conn, hall, resident, held):
    with pytest.raises(BookingConflict):
        lifecycle.place_hold(
            pg_conn,
            space_id=hall["space_id"],
            starts_at=S + timedelta(minutes=30),
            ends_at=E + timedelta(minutes=30),
            resident_id=resident,
        )


def test_back_to_back_is_fine(pg_conn, hall, resident, held):
    # tstzrange is [) so 19:00-20:00 doesn't touch 18:00-19:00
    b = lifecycle.place_hold(
        pg_conn, space_id=hall["space_id"], starts_at=E, ends_at=E + timedelta(hours=1), resident_id=resident
    )
    assert b.status == BookingStatus.HELD


def test_conflict_does_not_abort_outer_transaction(pg_conn, hall, resident, held):
    with pytest.raises(BookingConflict):
        lifecycle.place_hold(pg_conn, space_id=hall["space_id"], starts_at=S, ends_at=E, resident_id=resident)
    with pg_conn.cursor() as cur:
        cur.execute("SELECT 1")
        assert cur.fetchone() == (1,)


def test_org_on_account_books_straight_to_confirmed(pg_conn, hall, club, env):
    b = lifecycle.book_on_account(
        pg_conn,
        space_id=hall["space_id"],
        starts_at=S - timedelta(hours=1),
        ends_at=E + timedelta(hours=3),  # 17:00-22:00 local, 5h: fine for orgs
        organisation_id=club,
    )
    assert b.status == BookingStatus.CONFIRMED
    assert b.hold_expires_at is None
    assert env["sent"] == [("booking_confirmed", b.id)]


def test_resident_cannot_hold_five_hours(pg_conn, hall, resident, env):
    from hallpass.bookings.models import InvalidSlot

    with pytest.raises(InvalidSlot):
        lifecycle.place_hold(
            pg_conn,
            space_id=hall["space_id"],
            starts_at=S - timedelta(hours=1),
            ends_at=E + timedelta(hours=3),
            resident_id=resident,
        )


def test_confirm(pg_conn, held, sent):
    b = lifecycle.confirm(pg_conn, held.id, paybridge_payment_id="pb_pay_123")
    assert b.status == BookingStatus.CONFIRMED
    assert b.hold_expires_at is None
    assert sent[-1] == ("booking_confirmed", held.id)


def test_confirm_twice_is_idempotent(pg_conn, held, sent):
    lifecycle.confirm(pg_conn, held.id)
    lifecycle.confirm(pg_conn, held.id)
    assert [k for k, _ in sent].count("booking_confirmed") == 1


def test_late_payment_revives_hold_if_slot_still_free(pg_conn, held):
    lifecycle.cancel(pg_conn, held.id, reason=lifecycle.HOLD_EXPIRED, notify=False, promote_waitlist=False)
    b = lifecycle.confirm(pg_conn, held.id)
    assert b.status == BookingStatus.CONFIRMED


def test_late_payment_after_slot_taken(pg_conn, hall, second_resident, held):
    lifecycle.cancel(pg_conn, held.id, reason=lifecycle.HOLD_EXPIRED, notify=False, promote_waitlist=False)
    lifecycle.place_hold(pg_conn, space_id=hall["space_id"], starts_at=S, ends_at=E, resident_id=second_resident)
    with pytest.raises(HoldExpired):
        lifecycle.confirm(pg_conn, held.id)


def test_cancel_confirmed_requests_refund(pg_conn, held, refunds, sent):
    lifecycle.confirm(pg_conn, held.id)
    lifecycle.cancel(pg_conn, held.id, reason=lifecycle.CUSTOMER, promote_waitlist=False)
    assert refunds == [(held.id, False)]
    assert sent[-1] == ("booking_cancelled", held.id)


def test_closure_cancel_is_full_refund(pg_conn, held, refunds, sent):
    lifecycle.confirm(pg_conn, held.id)
    lifecycle.cancel(pg_conn, held.id, reason=lifecycle.CLOSURE, by_staff_id=1, promote_waitlist=False)
    assert refunds == [(held.id, True)]
    assert sent[-1] == ("booking_cancelled", held.id)


def test_staff_free_text_reason_is_a_normal_cancellation(pg_conn, held, refunds):
    lifecycle.confirm(pg_conn, held.id)
    b = lifecycle.cancel(pg_conn, held.id, reason="double booked by phone", by_staff_id=1, promote_waitlist=False)
    assert b.cancel_reason == "double booked by phone"
    assert refunds == [(held.id, False)]


def test_cancelling_a_hold_does_not_refund(pg_conn, held, refunds):
    lifecycle.cancel(pg_conn, held.id, reason=lifecycle.CUSTOMER, promote_waitlist=False)
    assert refunds == []


def test_cancel_frees_slot(pg_conn, hall, resident, held):
    lifecycle.cancel(pg_conn, held.id, reason=lifecycle.CUSTOMER, promote_waitlist=False)
    again = lifecycle.place_hold(pg_conn, space_id=hall["space_id"], starts_at=S, ends_at=E, resident_id=resident)
    assert again.id != held.id


def test_get_booking_missing(pg_conn):
    with pytest.raises(NotFound):
        lifecycle.get_booking(pg_conn, 99999999)


def test_no_show_window(pg_conn, held, frozen_now):
    lifecycle.confirm(pg_conn, held.id)
    frozen_now(S + timedelta(minutes=5))
    with pytest.raises(IllegalTransition, match="too early"):
        lifecycle.mark_no_show(pg_conn, held.id, staff_id=1)
    frozen_now(S + timedelta(minutes=20))
    assert lifecycle.mark_no_show(pg_conn, held.id, staff_id=1).status == BookingStatus.NO_SHOW


def test_cannot_cancel_no_show(pg_conn, held, frozen_now):
    lifecycle.confirm(pg_conn, held.id)
    frozen_now(S + timedelta(hours=1))
    lifecycle.mark_no_show(pg_conn, held.id, staff_id=1)
    with pytest.raises(IllegalTransition):
        lifecycle.cancel(pg_conn, held.id, reason=lifecycle.STAFF)


def test_release_expired_holds(pg_conn, held, frozen_now, sent):
    frozen_now(datetime(2025, 9, 1, 9, 14, tzinfo=UTC))
    assert jobs.release_expired_holds(pg_conn) == 0
    frozen_now(datetime(2025, 9, 1, 9, 16, tzinfo=UTC))
    assert jobs.release_expired_holds(pg_conn) == 1
    b = lifecycle.get_booking(pg_conn, held.id)
    assert (b.status, b.cancel_reason) == ("cancelled", "hold_expired")
    assert sent == []  # nobody is told about an abandoned checkout


def test_blackout_blocks_hold(pg_conn, hall, resident, env):
    with pg_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO blackout_periods (facility_id, space_id, starts_at, ends_at, reason, note, kind) "
            "VALUES (%s, %s, %s, %s, 'maintenance', 'floor sealing', 'maintenance')",
            (hall["facility_id"], hall["space_id"], S - timedelta(hours=3), E + timedelta(hours=3)),
        )
    with pytest.raises(BookingConflict, match="closed"):
        lifecycle.place_hold(pg_conn, space_id=hall["space_id"], starts_at=S, ends_at=E, resident_id=resident)
