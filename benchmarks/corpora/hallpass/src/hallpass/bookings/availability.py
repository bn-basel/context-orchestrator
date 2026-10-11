"""Availability search.

Given a set of spaces and a date range, work out which 30-minute slots are
free. Used by:

  * GET /api/bookings/availability   (public booking page, the hot path)
  * the facility page "this week" grid (all spaces, 7 days)
  * the staff diary (28 days)

How it works: one query pulls opening hours, one pulls everything that makes a
space busy (active bookings + blackout periods) for the whole window, then we
walk the slot grid in Python. Before Nov 2025 we did a query per space per day
and it fell over under load -- see docs/findings/bookings-availability-load-test-2025-11.md.

Search window is capped at 28 days. The public site only ever asks for 7.
"""

from __future__ import annotations

import bisect
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from psycopg import Connection
from psycopg.rows import dict_row

from hallpass.bookings.models import ACTIVE_STATUSES, FreeSlot
from hallpass.bookings.slots import slots_for_day
from hallpass.core.clock import now_utc
from hallpass.core.errors import NotFound
from hallpass.core.tz import local_day_bounds

MAX_WINDOW_DAYS = 28

# Don't show slots starting sooner than this. Gives the caretaker a chance to
# see the booking before people turn up. (Staff can still book "now".)
PUBLIC_LEAD_TIME = timedelta(hours=2)


@dataclass(slots=True)
class BusyRange:
    starts_at: datetime
    ends_at: datetime
    source: str  # 'booking' | 'blackout'
    held: bool = False


# One row per space per ISO weekday (UNIQUE in the schema). There is no notion
# of seasonal hours -- the grounds team change pitch hours by hand in April and
# October. See known issues (HP-470).
_OPENING_HOURS_SQL = """
SELECT oh.space_id, oh.weekday, oh.opens_at, oh.closes_at
FROM opening_hours oh
JOIN spaces s ON s.id = oh.space_id
WHERE oh.space_id = ANY(%(space_ids)s)
  AND s.is_bookable
"""

# NB: blackout_periods.space_id is NULL when the whole facility is closed
# (e.g. the building's fire alarm service). That's why we join on facility.
_BUSY_SQL = """
SELECT b.space_id, b.starts_at, b.ends_at, 'booking' AS source,
       (b.status = 'held') AS held
FROM bookings b
WHERE b.space_id = ANY(%(space_ids)s)
  AND b.status = ANY(%(active)s)
  AND tstzrange(b.starts_at, b.ends_at) && tstzrange(%(from_utc)s, %(to_utc)s)
UNION ALL
SELECT s.id AS space_id, bp.starts_at, bp.ends_at, 'blackout' AS source, false AS held
FROM blackout_periods bp
JOIN spaces s ON (bp.space_id = s.id OR (bp.space_id IS NULL AND bp.facility_id = s.facility_id))
WHERE s.id = ANY(%(space_ids)s)
  AND bp.withdrawn_at IS NULL
  AND tstzrange(bp.starts_at, bp.ends_at) && tstzrange(%(from_utc)s, %(to_utc)s)
ORDER BY 1, 2
"""


def spaces_for_facility(conn: Connection, facility_id: int) -> list[int]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM spaces WHERE facility_id = %s AND is_bookable ORDER BY sort_order, id",
            (facility_id,),
        )
        return [r[0] for r in cur.fetchall()]


def facility_for_space(conn: Connection, space_id: int) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT facility_id FROM spaces WHERE id = %s", (space_id,))
        row = cur.fetchone()
    if row is None:
        raise NotFound(f"space {space_id}")
    return row[0]


def busy_ranges(
    conn: Connection, space_ids: list[int], from_utc: datetime, to_utc: datetime
) -> dict[int, list[BusyRange]]:
    out: dict[int, list[BusyRange]] = defaultdict(list)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            _BUSY_SQL,
            {
                "space_ids": space_ids,
                "active": list(ACTIVE_STATUSES),
                "from_utc": from_utc,
                "to_utc": to_utc,
            },
        )
        for row in cur:
            out[row["space_id"]].append(
                BusyRange(row["starts_at"], row["ends_at"], row["source"], row["held"])
            )
    return out


def _hours_by_space(conn: Connection, space_ids: list[int]) -> dict[int, dict[int, tuple[time, time]]]:
    hours: dict[int, dict[int, tuple[time, time]]] = defaultdict(dict)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(_OPENING_HOURS_SQL, {"space_ids": space_ids})
        for row in cur:
            hours[row["space_id"]][row["weekday"]] = (row["opens_at"], row["closes_at"])
    return hours


def _overlaps(busy: list[BusyRange], starts: list[datetime], s: datetime, e: datetime) -> BusyRange | None:
    # busy is sorted by start; find anything that starts before e and ends after s.
    # Busy lists are short (tens of items per space per week) so the bisect is
    # mostly for show, but it did help on the 28-day staff view.
    idx = bisect.bisect_left(starts, e)
    for br in reversed(busy[:idx]):
        if br.ends_at > s:
            return br
    return None


def search(
    conn: Connection,
    *,
    space_ids: list[int],
    first_day: date,
    last_day: date,
    min_length: timedelta = timedelta(minutes=30),
    for_staff: bool = False,
    include_held: bool = False,
) -> list[FreeSlot]:
    """Return free slots, in order, for the given spaces and local dates (inclusive).

    ``min_length`` lets the public page ask "show me 1-hour gaps"; we then
    return only slot *starts* from which that much contiguous time is free.
    """
    if last_day < first_day:
        return []
    if (last_day - first_day).days >= MAX_WINDOW_DAYS:
        raise ValueError(f"availability window is limited to {MAX_WINDOW_DAYS} days")
    if not space_ids:
        return []

    from_utc, _ = local_day_bounds(first_day)
    _, until_utc = local_day_bounds(last_day)

    hours = _hours_by_space(conn, space_ids)
    busy = busy_ranges(conn, space_ids, from_utc, until_utc)
    earliest = now_utc() + (timedelta(0) if for_staff else PUBLIC_LEAD_TIME)

    results: list[FreeSlot] = []
    for space_id in space_ids:
        space_busy = busy.get(space_id, [])
        starts = [b.starts_at for b in space_busy]
        grid: list[tuple[datetime, datetime, bool]] = []

        day = first_day
        while day <= last_day:
            oh = hours.get(space_id, {}).get(day.isoweekday())
            if oh is not None:
                for s, e in slots_for_day(day, *oh):
                    if s < earliest:
                        continue
                    clash = _overlaps(space_busy, starts, s, e)
                    if clash is None:
                        grid.append((s, e, False))
                    elif include_held and clash.held:
                        grid.append((s, e, True))
            day += timedelta(days=1)

        results.extend(_runs_of_length(space_id, grid, min_length))

    results.sort(key=lambda fs: (fs.starts_at, fs.space_id))
    return results


def _runs_of_length(
    space_id: int, grid: list[tuple[datetime, datetime, bool]], min_length: timedelta
) -> list[FreeSlot]:
    """Keep slot starts that begin a contiguous free run of at least min_length."""
    out: list[FreeSlot] = []
    n = len(grid)
    for i, (s, e, held) in enumerate(grid):
        run_end = e
        j = i
        while run_end - s < min_length and j + 1 < n and grid[j + 1][0] == run_end:
            j += 1
            run_end = grid[j][1]
        if run_end - s >= min_length:
            out.append(FreeSlot(space_id, s, s + min_length, held_by_other=held))
    return out


def is_free(conn: Connection, space_id: int, starts_at: datetime, ends_at: datetime) -> bool:
    """Cheap pre-check before inserting. The exclusion constraint is the real
    guard (ADR 0009) -- this is only so we can give a nicer error message and
    skip a round trip to pricing when it's obviously taken."""
    ranges = busy_ranges(conn, [space_id], starts_at, ends_at).get(space_id, [])
    return not ranges
