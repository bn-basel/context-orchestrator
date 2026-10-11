from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from hallpass.bookings import availability, lifecycle

LON = ZoneInfo("Europe/London")
pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def _env(env):
    env["set_now"](datetime(2025, 9, 1, 6, 0, tzinfo=UTC))


def _local_starts(slots, day):
    return [s.starts_at.astimezone(LON).time() for s in slots if s.starts_at.astimezone(LON).date() == day]


def test_empty_day_has_28_half_hours(pg_conn, hall):
    slots = availability.search(
        pg_conn, space_ids=[hall["space_id"]], first_day=date(2025, 9, 3), last_day=date(2025, 9, 3)
    )
    assert len(slots) == 28  # 08:00-22:00


def test_booking_removes_slots(pg_conn, hall, resident):
    lifecycle.place_hold(
        pg_conn,
        space_id=hall["space_id"],
        starts_at=datetime(2025, 9, 3, 17, 0, tzinfo=UTC),
        ends_at=datetime(2025, 9, 3, 19, 0, tzinfo=UTC),
        resident_id=resident,
    )
    slots = availability.search(
        pg_conn, space_ids=[hall["space_id"]], first_day=date(2025, 9, 3), last_day=date(2025, 9, 3)
    )
    starts = _local_starts(slots, date(2025, 9, 3))
    assert time(18, 0) not in starts
    assert time(19, 30) not in starts
    assert time(20, 0) in starts
    assert len(slots) == 24


def test_held_slots_shown_when_asked(pg_conn, hall, resident):
    lifecycle.place_hold(
        pg_conn,
        space_id=hall["space_id"],
        starts_at=datetime(2025, 9, 3, 17, 0, tzinfo=UTC),
        ends_at=datetime(2025, 9, 3, 18, 0, tzinfo=UTC),
        resident_id=resident,
    )
    slots = availability.search(
        pg_conn,
        space_ids=[hall["space_id"]],
        first_day=date(2025, 9, 3),
        last_day=date(2025, 9, 3),
        include_held=True,
    )
    held = [s for s in slots if s.held_by_other]
    assert len(held) == 2


def test_min_length_two_hours(pg_conn, hall):
    slots = availability.search(
        pg_conn,
        space_ids=[hall["space_id"]],
        first_day=date(2025, 9, 3),
        last_day=date(2025, 9, 3),
        min_length=timedelta(hours=2),
    )
    starts = _local_starts(slots, date(2025, 9, 3))
    assert starts[-1] == time(20, 0)
    assert len(starts) == 25


def test_lead_time_hides_slots_too_soon(pg_conn, hall, frozen_now):
    frozen_now(datetime(2025, 9, 3, 9, 0, tzinfo=UTC))  # 10:00 BST
    slots = availability.search(
        pg_conn, space_ids=[hall["space_id"]], first_day=date(2025, 9, 3), last_day=date(2025, 9, 3)
    )
    assert _local_starts(slots, date(2025, 9, 3))[0] == time(12, 0)
    staff = availability.search(
        pg_conn, space_ids=[hall["space_id"]], first_day=date(2025, 9, 3), last_day=date(2025, 9, 3), for_staff=True
    )
    assert _local_starts(staff, date(2025, 9, 3))[0] == time(10, 0)


def test_facility_wide_blackout(pg_conn, hall):
    with pg_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO blackout_periods (facility_id, space_id, starts_at, ends_at, reason, note, kind) "
            "VALUES (%s, NULL, %s, %s, 'maintenance', 'fire alarm service', 'maintenance')",
            (hall["facility_id"], datetime(2025, 9, 3, 7, 0, tzinfo=UTC), datetime(2025, 9, 3, 11, 0, tzinfo=UTC)),
        )
    slots = availability.search(
        pg_conn, space_ids=[hall["space_id"]], first_day=date(2025, 9, 3), last_day=date(2025, 9, 3)
    )
    assert _local_starts(slots, date(2025, 9, 3))[0] == time(12, 0)


def test_legacy_quarter_hour_booking_blocks_both_neighbours(pg_conn, hall, club):
    # Old 15-minute-grid booking, 18:15-19:15, inserted directly (it predates
    # ADR 0011 and wouldn't pass validate_booking_window or the
    # bookings_slot_grid_30 check now -- the check is NOT VALID, so old rows stay).
    with pg_conn.cursor() as cur:
        # New :15 rows are refused by the grid check; drop it inside the test
        # transaction (rolled back afterwards) to fake a pre-2024 row.
        cur.execute("ALTER TABLE bookings DROP CONSTRAINT bookings_slot_grid_30")
        cur.execute(
            "INSERT INTO bookings (space_id, organisation_id, starts_at, ends_at, status, price_pence, created_at) "
            "VALUES (%s, %s, %s, %s, 'confirmed', 2500, now())",
            (hall["space_id"], club, datetime(2025, 9, 3, 17, 15, tzinfo=UTC), datetime(2025, 9, 3, 18, 15, tzinfo=UTC)),
        )
    slots = availability.search(
        pg_conn, space_ids=[hall["space_id"]], first_day=date(2025, 9, 3), last_day=date(2025, 9, 3)
    )
    starts = _local_starts(slots, date(2025, 9, 3))
    for t in (time(18, 0), time(18, 30), time(19, 0)):
        assert t not in starts
    assert time(19, 30) in starts


def test_clock_change_day(pg_conn, hall):
    slots = availability.search(
        pg_conn, space_ids=[hall["space_id"]], first_day=date(2025, 10, 26), last_day=date(2025, 10, 26)
    )
    assert len(slots) == 28
    assert _local_starts(slots, date(2025, 10, 26))[0] == time(8, 0)


def test_window_cap(pg_conn, hall):
    with pytest.raises(ValueError):
        availability.search(
            pg_conn, space_ids=[hall["space_id"]], first_day=date(2025, 9, 1), last_day=date(2025, 10, 1)
        )


def test_closed_weekday_has_no_slots(pg_conn, hall):
    with pg_conn.cursor() as cur:
        cur.execute("DELETE FROM opening_hours WHERE space_id = %s AND weekday = 7", (hall["space_id"],))
    assert availability.search(
        pg_conn, space_ids=[hall["space_id"]], first_day=date(2025, 9, 7), last_day=date(2025, 9, 7)
    ) == []
