from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from hallpass.bookings import lifecycle
from hallpass.bookings.models import SeriesSpec
from hallpass.bookings.recurring import (
    MAX_OCCURRENCES,
    SeriesRejected,
    cancel_series,
    create_series,
    occurrence_windows,
)
from hallpass.core.errors import HallpassError, ValidationError

LON = ZoneInfo("Europe/London")
TUESDAY = 2  # ISO


def spec(**kw):
    base = dict(
        space_id=1,
        organisation_id=7,
        resident_id=None,
        weekday=TUESDAY,
        start_time=time(19, 0),
        duration_minutes=120,
        first_date=date(2025, 9, 2),
        last_date=date(2025, 10, 21),
    )
    base.update(kw)
    return SeriesSpec(**base)


def test_weekly_occurrences_inside_summer_time():
    w = occurrence_windows(spec())
    assert len(w) == 8
    assert all(s.astimezone(LON).time() == time(19, 0) for s, _ in w)
    assert all((e - s).total_seconds() == 7200 for s, e in w)


def test_first_date_rolls_forward_to_weekday():
    w = occurrence_windows(spec(first_date=date(2025, 9, 1)))  # a Monday
    assert w[0][0].astimezone(LON).date() == date(2025, 9, 2)


def test_weekday_is_iso_not_python():
    # Regression: weekday=1 used to mean Tuesday here and Monday in the DB.
    w = occurrence_windows(spec(weekday=1))
    assert w[0][0].astimezone(LON).date() == date(2025, 9, 8)  # Monday


def test_fortnightly():
    w = occurrence_windows(spec(every_n_weeks=2))
    assert [s.astimezone(LON).date().day for s, _ in w] == [2, 16, 30, 14]


def test_empty_when_range_has_no_matching_weekday():
    assert occurrence_windows(spec(first_date=date(2025, 9, 3), last_date=date(2025, 9, 8))) == []


@pytest.mark.xfail(strict=True, reason="HP-503: series computed in UTC drift an hour after the clocks change")
def test_series_across_october_change_keeps_local_time():
    w = occurrence_windows(spec(last_date=date(2025, 12, 16)))
    assert {s.astimezone(LON).time() for s, _ in w} == {time(19, 0)}


def test_hp503_current_behaviour_is_pinned():
    # Pin the *current* wrong behaviour so whoever fixes HP-503 notices this
    # test and the xfails both flip. Remove all three when fixed.
    w = occurrence_windows(spec(last_date=date(2025, 11, 4)))
    by_date = {s.astimezone(LON).date(): s.astimezone(LON).time() for s, _ in w}
    assert by_date[date(2025, 10, 21)] == time(19, 0)
    assert by_date[date(2025, 10, 28)] == time(18, 0)  # wrong, should be 19:00
    assert by_date[date(2025, 11, 4)] == time(18, 0)


@pytest.mark.xfail(strict=True, reason="HP-503 again, the spring direction")
def test_series_across_march_change_keeps_local_time():
    w = occurrence_windows(
        spec(first_date=date(2026, 3, 3), last_date=date(2026, 4, 28), start_time=time(18, 30))
    )
    assert {s.astimezone(LON).time() for s, _ in w} == {time(18, 30)}


def test_split_at_clock_change_workaround_is_correct():
    # What the how-to tells the bookings officer to do. Each part on its own
    # side of the change => every occurrence at 19:00.
    parts = [
        spec(first_date=date(2025, 9, 2), last_date=date(2025, 10, 21)),
        spec(first_date=date(2025, 10, 28), last_date=date(2026, 3, 24)),
        spec(first_date=date(2026, 3, 31), last_date=date(2026, 7, 7)),
    ]
    for p in parts:
        assert {s.astimezone(LON).time() for s, _ in occurrence_windows(p)} == {time(19, 0)}


def test_too_many_occurrences():
    s = spec(first_date=date(2025, 1, 7), last_date=date(2026, 6, 30))
    assert len(occurrence_windows(s)) > MAX_OCCURRENCES


# --- DB tests ---------------------------------------------------------------


@pytest.fixture
def _august(env):
    env["set_now"](datetime(2025, 8, 20, 10, 0, tzinfo=UTC))


@pytest.mark.db
def test_create_series_for_club(pg_conn, hall, club, env, _august):
    res = create_series(pg_conn, spec(space_id=hall["space_id"], organisation_id=club))
    assert len(res.booking_ids) == 8
    with pg_conn.cursor() as cur:
        cur.execute("SELECT count(*), sum(price_pence) FROM bookings WHERE series_id = %s", (res.series_id,))
        n, total = cur.fetchone()
    assert n == 8
    assert total == 8 * 4000
    assert env["sent"] == [("series_confirmed", res.series_id)]  # one email, not eight


@pytest.mark.db
def test_series_all_or_nothing_on_conflict(pg_conn, hall, club, second_resident, env, _august):
    lifecycle.place_hold(
        pg_conn,
        space_id=hall["space_id"],
        starts_at=datetime(2025, 9, 16, 18, 0, tzinfo=UTC),  # 19:00 BST
        ends_at=datetime(2025, 9, 16, 19, 0, tzinfo=UTC),
        resident_id=second_resident,
    )
    with pytest.raises(SeriesRejected) as exc:
        create_series(pg_conn, spec(space_id=hall["space_id"], organisation_id=club))
    assert len(exc.value.conflicts) == 1


@pytest.mark.db
def test_series_skip_conflicts_for_staff(pg_conn, hall, club, second_resident, env, _august):
    lifecycle.place_hold(
        pg_conn,
        space_id=hall["space_id"],
        starts_at=datetime(2025, 9, 16, 18, 0, tzinfo=UTC),
        ends_at=datetime(2025, 9, 16, 19, 0, tzinfo=UTC),
        resident_id=second_resident,
    )
    res = create_series(
        pg_conn, spec(space_id=hall["space_id"], organisation_id=club), staff_id=1, skip_conflicts=True
    )
    assert len(res.booking_ids) == 7
    assert res.skipped_conflict == [date(2025, 9, 16)]


@pytest.mark.db
def test_series_skips_blackout_silently(pg_conn, hall, club, env, _august):
    with pg_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO blackout_periods (facility_id, space_id, starts_at, ends_at, reason, note, kind) "
            "VALUES (%s, NULL, %s, %s, 'event', 'polling station', 'event')",
            (hall["facility_id"], datetime(2025, 9, 30, 5, 0, tzinfo=UTC), datetime(2025, 9, 30, 22, 0, tzinfo=UTC)),
        )
    res = create_series(pg_conn, spec(space_id=hall["space_id"], organisation_id=club))
    assert res.skipped_closure == [date(2025, 9, 30)]
    assert len(res.booking_ids) == 7
    # NB: series is NOT extended to make up the lost week. Intended? See
    # docs/bookings/blackouts-and-series.md


@pytest.mark.db
def test_too_many_occurrences_rejected(pg_conn, hall, club, env, _august):
    with pytest.raises(ValidationError, match="limit"):
        create_series(
            pg_conn,
            spec(space_id=hall["space_id"], organisation_id=club, last_date=date(2026, 12, 1)),
        )


@pytest.mark.db
def test_cancel_series_leaves_past_sessions(pg_conn, hall, club, resident, env, _august):
    res = create_series(pg_conn, spec(space_id=hall["space_id"], organisation_id=club))
    env["set_now"](datetime(2025, 9, 20, 10, 0, tzinfo=UTC))
    cancelled = cancel_series(pg_conn, res.series_id, reason="customer")
    assert len(cancelled) == 5  # 23 Sep .. 21 Oct
    assert env["sent"][-1] == ("series_cancelled", res.series_id)
    assert [t for t, _ in env["sent"]].count("booking_cancelled") == 0


@pytest.mark.db
def test_resident_cannot_make_own_series(pg_conn, hall, resident, env, _august):
    with pytest.raises(HallpassError, match="only organisations or staff"):
        create_series(pg_conn, spec(space_id=hall["space_id"], organisation_id=None, resident_id=resident))
