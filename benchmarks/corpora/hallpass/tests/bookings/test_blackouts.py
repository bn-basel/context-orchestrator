from datetime import UTC, date, datetime, time

import pytest

from hallpass.bookings import availability, blackouts, lifecycle
from hallpass.bookings.models import SeriesSpec
from hallpass.bookings.recurring import create_series
from hallpass.core.errors import ValidationError

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def _env(env):
    env["set_now"](datetime(2025, 8, 20, 9, 0, tzinfo=UTC))


def _club_series(pg_conn, hall, club):
    return create_series(
        pg_conn,
        SeriesSpec(
            space_id=hall["space_id"],
            organisation_id=club,
            resident_id=None,
            weekday=2,  # Tuesday
            start_time=time(19, 0),
            duration_minutes=120,
            first_date=date(2025, 9, 2),
            last_date=date(2025, 10, 21),
        ),
    )


def _close_two_tuesdays(pg_conn, hall, *, space_id=None, cancel_affected=False):
    return blackouts.create_blackout(
        pg_conn,
        facility_id=hall["facility_id"],
        space_id=space_id,
        starts_at=datetime(2025, 9, 9, 0, 0, tzinfo=UTC),
        ends_at=datetime(2025, 9, 17, 0, 0, tzinfo=UTC),
        reason="maintenance",
        note="roof repairs",
        kind="maintenance",
        staff_id=1,
        cancel_affected=cancel_affected,
    )


def test_refuses_when_bookings_affected(pg_conn, hall, club):
    _club_series(pg_conn, hall, club)
    with pytest.raises(blackouts.BlackoutClashes) as exc:
        _close_two_tuesdays(pg_conn, hall)
    assert len(exc.value.affected) == 2
    assert exc.value.affected[0].hirer_name == "Thornbury Badminton Club"
    with pg_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM blackout_periods WHERE facility_id = %s", (hall["facility_id"],))
        assert cur.fetchone()[0] == 0  # nothing saved


def test_cancel_affected_cancels_series_occurrences(pg_conn, hall, club, env):
    s = _club_series(pg_conn, hall, club)
    res = _close_two_tuesdays(pg_conn, hall, space_id=hall["space_id"], cancel_affected=True)

    assert len(res.cancelled_ids) == 2
    assert res.affected_series_ids == [s.series_id]
    assert all(full for _, full in env["refunds"])  # closure => full refund
    # one summary for the club, not one email per lost week
    assert [m for m in env["sent"] if m[0] != "series_confirmed"] == [("series_sessions_closed", s.series_id)]

    with pg_conn.cursor() as cur:
        cur.execute("SELECT last_date FROM booking_series WHERE id = %s", (s.series_id,))
        (last_date,) = cur.fetchone()
    # Current behaviour: the series is NOT extended. Open question whether it
    # should be -- don't "fix" this test without a decision.
    assert last_date == date(2025, 10, 21)


def test_closure_hides_slots(pg_conn, hall):
    _close_two_tuesdays(pg_conn, hall)
    assert availability.search(
        pg_conn, space_ids=[hall["space_id"]], first_day=date(2025, 9, 10), last_day=date(2025, 9, 10)
    ) == []


def test_withdraw_does_not_restore_bookings(pg_conn, hall, resident):
    b = lifecycle.place_hold(
        pg_conn,
        space_id=hall["space_id"],
        starts_at=datetime(2025, 9, 10, 17, 0, tzinfo=UTC),
        ends_at=datetime(2025, 9, 10, 18, 0, tzinfo=UTC),
        resident_id=resident,
    )
    lifecycle.confirm(pg_conn, b.id)
    res = blackouts.create_blackout(
        pg_conn,
        facility_id=hall["facility_id"],
        space_id=hall["space_id"],
        starts_at=datetime(2025, 9, 10, 7, 0, tzinfo=UTC),
        ends_at=datetime(2025, 9, 10, 21, 0, tzinfo=UTC),
        reason="weather",
        note="waterlogged",
        kind="weather",
        staff_id=1,
        cancel_affected=True,
    )
    blackouts.withdraw_blackout(pg_conn, res.blackout_id, staff_id=1)
    assert lifecycle.get_booking(pg_conn, b.id).status == "cancelled"


@pytest.mark.parametrize("reason", ["because", "Maintenance", ""])
def test_unknown_reason(pg_conn, hall, reason):
    with pytest.raises(ValidationError, match="unknown closure reason"):
        blackouts.create_blackout(
            pg_conn,
            facility_id=hall["facility_id"],
            space_id=None,
            starts_at=datetime(2025, 9, 10, 7, 0, tzinfo=UTC),
            ends_at=datetime(2025, 9, 10, 21, 0, tzinfo=UTC),
            reason=reason,
            note="",
            staff_id=1,
        )
