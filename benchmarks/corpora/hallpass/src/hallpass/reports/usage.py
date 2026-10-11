"""Usage / utilisation report.

Utilisation = booked hours / available hours, per space, over a local date
range. 'Available' is opening hours minus blackouts (closures, maintenance
windows etc.). No-shows count as booked - the space was unavailable to anyone
else - but they're reported in their own column because the service managers
want to chase repeat offenders.

Dates are Europe/London calendar dates, inclusive on both ends.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from hallpass.core import db, tz

_BOOKED_SQL = """
SELECT
    s.id                                    AS space_id,
    s.name                                  AS space_name,
    f.id                                    AS facility_id,
    f.name                                  AS facility_name,
    count(*) FILTER (WHERE b.status = 'confirmed')            AS confirmed_count,
    count(*) FILTER (WHERE b.status = 'no_show')              AS no_show_count,
    count(*) FILTER (WHERE b.status = 'cancelled')            AS cancelled_count,
    coalesce(sum(extract(epoch FROM b.ends_at - b.starts_at) / 3600.0)
        FILTER (WHERE b.status IN ('confirmed', 'no_show')), 0)  AS booked_hours,
    count(DISTINCT b.series_id) FILTER (WHERE b.series_id IS NOT NULL) AS series_count
FROM spaces s
JOIN facilities f ON f.id = s.facility_id
LEFT JOIN bookings b
       ON b.space_id = s.id
      AND b.starts_at >= %(start)s
      AND b.starts_at <  %(end)s
WHERE (%(facility_id)s::bigint IS NULL OR f.id = %(facility_id)s::bigint)
GROUP BY s.id, s.name, f.id, f.name
ORDER BY f.name, s.name
"""

_OPENING_SQL = """
SELECT space_id, weekday, opens_at, closes_at
FROM opening_hours
WHERE (%(facility_id)s::bigint IS NULL
       OR space_id IN (SELECT id FROM spaces WHERE facility_id = %(facility_id)s::bigint))
"""

_BLACKOUT_SQL = """
SELECT
    coalesce(bp.space_id, s.id) AS space_id,
    sum(extract(epoch FROM least(bp.ends_at, %(end)s) - greatest(bp.starts_at, %(start)s)) / 3600.0) AS hours
FROM blackout_periods bp
JOIN spaces s ON s.facility_id = bp.facility_id AND (bp.space_id IS NULL OR bp.space_id = s.id)
WHERE bp.starts_at < %(end)s AND bp.ends_at > %(start)s
GROUP BY 1
"""


def _open_hours(opening: list[dict[str, Any]], space_id: int, start: date, end: date) -> float:
    by_weekday = {r["weekday"]: r for r in opening if r["space_id"] == space_id}
    total = 0.0
    day = start
    while day <= end:
        row = by_weekday.get(day.isoweekday())
        if row:
            opens = row["opens_at"].hour + row["opens_at"].minute / 60
            closes = row["closes_at"].hour + row["closes_at"].minute / 60
            total += closes - opens
        day += timedelta(days=1)
    # NB: ignores the DST hour. Facilities are shut at 1am so it doesn't matter.
    return total


def space_utilisation(conn, *, start: date, end: date, facility_id: int | None = None) -> list[dict[str, Any]]:
    range_start, _ = tz.local_day_bounds(start)
    _, range_end = tz.local_day_bounds(end)
    params = {"start": range_start, "end": range_end, "facility_id": facility_id}

    booked = db.fetch_all(conn, _BOOKED_SQL, params)
    opening = db.fetch_all(conn, _OPENING_SQL, params)
    blackout_hours = {r["space_id"]: float(r["hours"]) for r in db.fetch_all(conn, _BLACKOUT_SQL, params)}

    out = []
    for row in booked:
        # TODO: blackout hours outside opening hours are still subtracted here,
        # so overnight maintenance windows make utilisation look better than it is.
        available = max(_open_hours(opening, row["space_id"], start, end) - blackout_hours.get(row["space_id"], 0.0), 0.0)
        booked_hours = float(row["booked_hours"])
        out.append(
            {
                **row,
                "booked_hours": round(booked_hours, 1),
                "available_hours": round(available, 1),
                "utilisation_pct": round(100 * booked_hours / available, 1) if available else None,
            }
        )
    return out


def peak_hours(conn, *, start: date, end: date, facility_id: int) -> list[dict[str, Any]]:
    """Bookings by local weekday and hour, for the 'when is it busy' chart."""
    range_start, _ = tz.local_day_bounds(start)
    _, range_end = tz.local_day_bounds(end)
    return db.fetch_all(
        conn,
        """
        SELECT
            extract(isodow FROM b.starts_at AT TIME ZONE 'Europe/London')::int AS weekday,
            extract(hour   FROM b.starts_at AT TIME ZONE 'Europe/London')::int AS hour,
            count(*) AS bookings
        FROM bookings b
        JOIN spaces s ON s.id = b.space_id
        WHERE s.facility_id = %(facility_id)s
          AND b.status IN ('confirmed', 'no_show')
          AND b.starts_at >= %(start)s AND b.starts_at < %(end)s
        GROUP BY 1, 2
        ORDER BY 1, 2
        """,
        {"facility_id": facility_id, "start": range_start, "end": range_end},
    )
