"""Blackouts, a.k.a. closures / maintenance windows.

A blackout_periods row closes either one space (space_id set) or a whole
facility (space_id NULL) between two instants. Examples: floor resurfacing in
Hall B, polling-station days, the annual fire-alarm service, pitches closed
because they're waterlogged.

Columns: ``reason`` is a short code from the staff dropdown (REASONS below),
``note`` is free text that hirers see in the cancellation message, and
``kind`` (closure | maintenance | event | weather) was added in migration
0009 so reports can tell maintenance apart. Yes, reason and kind overlap.
The staff screen sets kind from reason; the API defaults it to 'closure'.

Blackouts don't go through the exclusion constraint (that's on bookings
only), so availability and lifecycle check them explicitly.

Creating a blackout over existing bookings:

  * default: refuse with BlackoutClashes (the API turns it into a 409 listing
    the bookings) so staff can see who they'd be letting down
  * ``cancel_affected=True``: cancel them with reason 'closure', which billing
    treats as a full refund irrespective of notice (council's fault, not the
    hirer's)

What we *don't* do anything clever about is series. If the blackout eats
three Tuesdays out of a club's block booking, those three occurrences are
cancelled and that's it -- the series isn't extended and nobody is offered a
replacement slot. Whether we should is still undecided; see
docs/bookings/blackouts-and-series.md. Leisure Services keep asking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from psycopg import Connection
from psycopg.rows import dict_row

from hallpass.bookings import lifecycle
from hallpass.core.audit import write_audit
from hallpass.core.clock import now_utc
from hallpass.core.errors import ConflictError, NotFound, ValidationError
from hallpass.notifications.outbox import enqueue

REASONS = {
    "maintenance",
    "event",  # council use: elections, emergency rest centre, etc.
    "weather",  # pitches
    "staffing",
    "other",
}
KINDS = ("closure", "maintenance", "event", "weather")


@dataclass(slots=True)
class AffectedBooking:
    booking_id: int
    space_id: int
    starts_at: datetime
    ends_at: datetime
    status: str
    series_id: int | None
    hirer_name: str


@dataclass(slots=True)
class BlackoutResult:
    blackout_id: int | None
    affected: list[AffectedBooking] = field(default_factory=list)
    cancelled_ids: list[int] = field(default_factory=list)
    affected_series_ids: list[int] = field(default_factory=list)  # list, not set: to_json can't do sets


class BlackoutClashes(ConflictError):
    def __init__(self, affected: list[AffectedBooking]):
        super().__init__(f"{len(affected)} booking(s) fall inside this closure")
        self.affected = affected


_AFFECTED_SQL = """
SELECT b.id AS booking_id, b.space_id, b.starts_at, b.ends_at, b.status, b.series_id,
       COALESCE(o.name, r.display_name, r.email, '(unknown)') AS hirer_name
FROM bookings b
JOIN spaces s ON s.id = b.space_id
LEFT JOIN organisations o ON o.id = b.organisation_id
LEFT JOIN residents r ON r.id = b.resident_id
WHERE b.status IN ('held', 'confirmed')
  AND s.facility_id = %(facility_id)s
  AND (%(space_id)s::bigint IS NULL OR s.id = %(space_id)s)
  AND tstzrange(b.starts_at, b.ends_at) && tstzrange(%(starts_at)s, %(ends_at)s)
ORDER BY b.starts_at
"""


def find_affected(
    conn: Connection, *, facility_id: int, space_id: int | None, starts_at: datetime, ends_at: datetime
) -> list[AffectedBooking]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            _AFFECTED_SQL,
            {"facility_id": facility_id, "space_id": space_id, "starts_at": starts_at, "ends_at": ends_at},
        )
        return [AffectedBooking(**row) for row in cur.fetchall()]


def create_blackout(
    conn: Connection,
    *,
    facility_id: int,
    space_id: int | None,
    starts_at: datetime,
    ends_at: datetime,
    reason: str,
    note: str,
    staff_id: int,
    cancel_affected: bool = False,
    kind: str = "closure",
) -> BlackoutResult:
    if reason not in REASONS:
        raise ValidationError(f"unknown closure reason {reason!r}")
    if kind not in KINDS:
        raise ValidationError(f"unknown closure kind {kind!r}")
    if ends_at <= starts_at:
        raise ValidationError("closure must end after it starts")
    # NB: no slot-grid check here on purpose. Closures can be any length
    # (the boiler engineer arrives at 07:40, not 07:30).

    affected = find_affected(
        conn, facility_id=facility_id, space_id=space_id, starts_at=starts_at, ends_at=ends_at
    )
    if affected and not cancel_affected:
        raise BlackoutClashes(affected)

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO blackout_periods (facility_id, space_id, starts_at, ends_at, reason, note, kind,
                                          created_by_staff_id, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (facility_id, space_id, starts_at, ends_at, reason, note, kind, staff_id, now_utc()),
        )
        (blackout_id,) = cur.fetchone()  # type: ignore[misc]

    result = BlackoutResult(blackout_id=blackout_id, affected=affected)
    for a in affected:
        # promote_waitlist=False: there's nothing to promote into, it's closed.
        # Series occurrences don't get individual emails; the club gets one
        # series_sessions_closed per series below.
        lifecycle.cancel(
            conn,
            a.booking_id,
            reason=lifecycle.CLOSURE,
            by_staff_id=staff_id,
            notify=a.series_id is None,
            promote_waitlist=False,
        )
        result.cancelled_ids.append(a.booking_id)
        if a.series_id is not None and a.series_id not in result.affected_series_ids:
            result.affected_series_ids.append(a.series_id)

    # TODO: decide what happens to series here. For now we just tell the org
    # which dates went. (Open question, see blackouts-and-series.md.)
    for sid in result.affected_series_ids:
        enqueue(conn, template="series_sessions_closed", series_id=sid, blackout_id=blackout_id)

    write_audit(
        conn,
        actor_staff_id=staff_id,
        action="blackout.create",
        entity="blackout_periods",
        entity_id=blackout_id,
        detail={"cancelled": result.cancelled_ids, "reason": reason, "kind": kind},
    )
    return result


def withdraw_blackout(conn: Connection, blackout_id: int, *, staff_id: int) -> None:
    """Re-open. Bookings cancelled because of the closure are NOT restored --
    their refunds may already have gone out. Staff have to rebook by hand if
    the hirer still wants it."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE blackout_periods SET withdrawn_at = %s, withdrawn_by_staff_id = %s "
            "WHERE id = %s AND withdrawn_at IS NULL",
            (now_utc(), staff_id, blackout_id),
        )
        if cur.rowcount == 0:
            raise NotFound("closure not found or already withdrawn")
    write_audit(conn, actor_staff_id=staff_id, action="blackout.withdraw", entity="blackout_periods", entity_id=blackout_id)


def list_upcoming(conn: Connection, facility_id: int) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT bp.*, sp.name AS space_name
            FROM blackout_periods bp
            LEFT JOIN spaces sp ON sp.id = bp.space_id
            WHERE bp.facility_id = %s AND bp.withdrawn_at IS NULL AND bp.ends_at > %s
            ORDER BY bp.starts_at
            """,
            (facility_id, now_utc()),
        )
        return list(cur.fetchall())
