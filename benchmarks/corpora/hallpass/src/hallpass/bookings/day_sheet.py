"""The caretaker's day sheet.

One page per facility per day: every space, every booking, who's coming,
plus closures. Printed at most centres at 07:00 and pinned up in the office;
the no-show button on the staff screen hangs off the same data.

Times are local. Cancelled bookings are left off; held ones are shown
(marked "unpaid") because by the time the caretaker reads it they've usually
been paid.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row

from hallpass.core.tz import format_local, local_day_bounds

_SQL = """
SELECT sp.id AS space_id, sp.name AS space_name, sp.sort_order,
       b.id AS booking_id, b.starts_at, b.ends_at, b.status, b.series_id,
       COALESCE(o.name, r.display_name, '(no name)') AS hirer,
       r.mobile AS contact_mobile
FROM spaces sp
LEFT JOIN bookings b
       ON b.space_id = sp.id
      AND b.status IN ('held', 'confirmed', 'no_show')
      AND tstzrange(b.starts_at, b.ends_at) && tstzrange(%(start)s, %(end)s)
LEFT JOIN organisations o ON o.id = b.organisation_id
LEFT JOIN residents r ON r.id = b.resident_id
WHERE sp.facility_id = %(facility_id)s
ORDER BY sp.sort_order, sp.id, b.starts_at
"""

_CLOSURES_SQL = """
SELECT bp.space_id, bp.starts_at, bp.ends_at, bp.kind, bp.reason
FROM blackout_periods bp
WHERE bp.facility_id = %(facility_id)s
  AND bp.withdrawn_at IS NULL
  AND tstzrange(bp.starts_at, bp.ends_at) && tstzrange(%(start)s, %(end)s)
"""


def build(conn: Connection, *, facility_id: int, day: date) -> dict[str, Any]:
    start, end = local_day_bounds(day)
    params = {"facility_id": facility_id, "start": start, "end": end}

    spaces: dict[int, dict[str, Any]] = {}
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(_SQL, params)
        for row in cur:
            sp = spaces.setdefault(
                row["space_id"],
                {"space_id": row["space_id"], "name": row["space_name"], "bookings": [], "closures": []},
            )
            if row["booking_id"] is None:
                continue
            sp["bookings"].append(
                {
                    "booking_id": row["booking_id"],
                    "time": f"{format_local(row['starts_at'], '%H:%M')}-{format_local(row['ends_at'], '%H:%M')}",
                    "hirer": row["hirer"],
                    # Caretakers asked for a phone number; residents only.
                    # Org contacts are on the club's file in the office.
                    "contact": row["contact_mobile"],
                    "unpaid": row["status"] == "held",
                    "no_show": row["status"] == "no_show",
                    "block_booking": row["series_id"] is not None,
                }
            )

        cur.execute(_CLOSURES_SQL, params)
        closures = cur.fetchall()

    by_space: dict[int | None, list[dict]] = defaultdict(list)
    for c in closures:
        by_space[c["space_id"]].append(
            {
                "time": f"{format_local(c['starts_at'], '%d/%m %H:%M')}-{format_local(c['ends_at'], '%d/%m %H:%M')}",
                "kind": c["kind"],
                "reason": c["reason"],
            }
        )
    for sid, sp in spaces.items():
        sp["closures"] = by_space.get(sid, []) + by_space.get(None, [])

    return {
        "facility_id": facility_id,
        "date": day.isoformat(),
        "is_clock_change_day": (end - start).total_seconds() != 86400,
        "spaces": list(spaces.values()),
    }
