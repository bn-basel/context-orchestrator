"""Booking lifecycle: hold -> confirmed -> (cancelled | no_show).

    held ──confirm()──▶ confirmed ──cancel()──▶ cancelled
     │                     │
     │ expire / cancel     └──mark_no_show()──▶ no_show
     ▼
    cancelled

Card customers (residents, mostly) get a *hold* while they're on the Paybridge
hosted checkout. The hold occupies the slot -- it's covered by the exclusion
constraint just like a confirmed booking -- so nobody else can grab it while
they type their card number. If the payment webhook doesn't arrive in time
jobs.release_expired_holds cancels it.

Organisations on account (``organisations.on_account``) skip the hold and go
straight to confirmed; billing puts it on next month's invoice.

Concurrency: we don't lock anything up front. We INSERT and let the
``bookings_no_overlap`` exclusion constraint reject clashes (ADR 0009). The
constraint violation surfaces as psycopg.errors.ExclusionViolation, which we
turn into BookingConflict.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from psycopg import Connection, errors
from psycopg.rows import dict_row

from hallpass.billing.pricing import quote_price
from hallpass.bookings.models import (
    Booking,
    BookingConflict,
    BookingStatus,
    HoldExpired,
    IllegalTransition,
)
from hallpass.bookings.slots import validate_booking_window
from hallpass.core.audit import write_audit
from hallpass.core.clock import now_utc
from hallpass.core.config import get_settings
from hallpass.core.errors import NotFound
from hallpass.notifications.outbox import enqueue

log = logging.getLogger(__name__)


def hold_ttl() -> timedelta:
    # 15 minutes by default (HALLPASS_HOLD_MINUTES). Was 10 at launch; changed
    # in 2.5.0 after the May 2024 meeting because 3-D Secure on phones kept
    # outlasting it. See docs/meetings/2024-05-14-holds-and-no-shows.md.
    return timedelta(minutes=get_settings().hold_minutes)


# Staff can mark a no-show from 15 minutes after the start until 7 days later.
NO_SHOW_GRACE = timedelta(minutes=15)
NO_SHOW_WINDOW = timedelta(days=7)

# cancel_reason values. Billing keys refund behaviour off these, so don't
# invent new ones without telling them.
CUSTOMER = "customer"  # hirer cancelled; tiered refund (ADR 0012)
STAFF = "staff"  # staff cancelled on the hirer's behalf; tiered refund
CLOSURE = "closure"  # council's fault: full refund whatever the notice
HOLD_EXPIRED = "hold_expired"  # nothing was paid

_INSERT_SQL = """
INSERT INTO bookings (space_id, resident_id, organisation_id, series_id,
                      starts_at, ends_at, status, price_pence, hold_expires_at,
                      created_at, created_by_staff_id)
VALUES (%(space_id)s, %(resident_id)s, %(organisation_id)s, %(series_id)s,
        %(starts_at)s, %(ends_at)s, %(status)s, %(price_pence)s, %(hold_expires_at)s,
        %(now)s, %(staff_id)s)
RETURNING *
"""


def _insert(conn: Connection, params: dict) -> Booking:
    try:
        # Savepoint so a conflict doesn't poison the caller's transaction
        # (recurring.py relies on this when it inserts 40 rows in a loop).
        with conn.transaction():
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_INSERT_SQL, params)
                row = cur.fetchone()
    except errors.ExclusionViolation as exc:
        raise BookingConflict(
            "that time is no longer available",
            space_id=params["space_id"],
            starts_at=params["starts_at"],
            ends_at=params["ends_at"],
        ) from exc
    assert row is not None
    return Booking.from_row(row)


def get_booking(conn: Connection, booking_id: int, *, for_update: bool = False) -> Booking:
    sql = "SELECT * FROM bookings WHERE id = %s"
    if for_update:
        sql += " FOR UPDATE"
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, (booking_id,))
        row = cur.fetchone()
    if row is None:
        raise NotFound(f"booking {booking_id}")
    return Booking.from_row(row)


def _blackout_clash(conn: Connection, space_id: int, starts_at: datetime, ends_at: datetime) -> bool:
    # Blackouts are NOT in the exclusion constraint (different table), so we
    # have to check them by hand. There's a tiny window where a blackout can
    # be created between this check and the insert (HP-611). Not worth a lock.
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM blackout_periods bp
            JOIN spaces s ON s.id = %(space_id)s
            WHERE (bp.space_id = s.id OR (bp.space_id IS NULL AND bp.facility_id = s.facility_id))
              AND bp.withdrawn_at IS NULL
              AND tstzrange(bp.starts_at, bp.ends_at) && tstzrange(%(s)s, %(e)s)
            LIMIT 1
            """,
            {"space_id": space_id, "s": starts_at, "e": ends_at},
        )
        return cur.fetchone() is not None


def place_hold(
    conn: Connection,
    *,
    space_id: int,
    starts_at: datetime,
    ends_at: datetime,
    resident_id: int | None,
    organisation_id: int | None = None,
    staff_id: int | None = None,
    ttl: timedelta | None = None,
) -> Booking:
    """Reserve a slot for a short while (hold_ttl()) while the customer pays."""
    validate_booking_window(
        starts_at, ends_at, is_staff=staff_id is not None, is_organisation=organisation_id is not None
    )
    if _blackout_clash(conn, space_id, starts_at, ends_at):
        raise BookingConflict(
            "the space is closed at that time", space_id=space_id, starts_at=starts_at, ends_at=ends_at
        )

    now = now_utc()
    price = quote_price(
        conn,
        space_id=space_id,
        starts_at=starts_at,
        ends_at=ends_at,
        resident_id=resident_id,
        organisation_id=organisation_id,
    )
    booking = _insert(
        conn,
        {
            "space_id": space_id,
            "resident_id": resident_id,
            "organisation_id": organisation_id,
            "series_id": None,
            "starts_at": starts_at,
            "ends_at": ends_at,
            "status": BookingStatus.HELD,
            "price_pence": price.total_pence,
            "hold_expires_at": now + (ttl or hold_ttl()),
            "now": now,
            "staff_id": staff_id,
        },
    )
    write_audit(conn, actor_staff_id=staff_id, action="booking.hold", entity="bookings", entity_id=booking.id)
    return booking


def book_on_account(
    conn: Connection,
    *,
    space_id: int,
    starts_at: datetime,
    ends_at: datetime,
    organisation_id: int,
    resident_id: int | None = None,
    staff_id: int | None = None,
    series_id: int | None = None,
) -> Booking:
    """Organisations on account (``organisations.on_account``): straight to
    confirmed, no hold, no Paybridge. The API calls this from /org-booking."""
    validate_booking_window(starts_at, ends_at, is_staff=staff_id is not None, is_organisation=True)
    if _blackout_clash(conn, space_id, starts_at, ends_at):
        raise BookingConflict(
            "the space is closed at that time", space_id=space_id, starts_at=starts_at, ends_at=ends_at
        )
    now = now_utc()
    price = quote_price(
        conn,
        space_id=space_id,
        starts_at=starts_at,
        ends_at=ends_at,
        resident_id=None,
        organisation_id=organisation_id,
    )
    booking = _insert(
        conn,
        {
            "space_id": space_id,
            # resident_id here is "who made it" for org bookings; billing
            # ignores it and invoices the org.
            "resident_id": resident_id,
            "organisation_id": organisation_id,
            "series_id": series_id,
            "starts_at": starts_at,
            "ends_at": ends_at,
            "status": BookingStatus.CONFIRMED,
            "price_pence": price.total_pence,
            "hold_expires_at": None,
            "now": now,
            "staff_id": staff_id,
        },
    )
    # Invoice line is added by billing's monthly invoice run, not here. (It
    # used to be here; moved so series don't create 40 lines one by one.)
    if series_id is None:
        enqueue(conn, template="booking_confirmed", booking_id=booking.id)
    return booking


def confirm(conn: Connection, booking_id: int, *, paybridge_payment_id: str | None = None) -> Booking:
    """Move a hold to confirmed. Called by billing once the Paybridge payment
    has succeeded (and for zero-price bookings, which skip Paybridge)."""
    booking = get_booking(conn, booking_id, for_update=True)

    if booking.status == BookingStatus.CONFIRMED:
        # Duplicate webhook. Fine, nothing to do.
        return booking
    if booking.status == BookingStatus.CANCELLED and booking.cancel_reason == HOLD_EXPIRED:
        # Paid after the hold lapsed. Revive it if the slot is still free --
        # the exclusion constraint will tell us. Otherwise raise HoldExpired
        # and billing deals with the money.
        try:
            return _revive_expired_hold(conn, booking)
        except BookingConflict as exc:
            raise HoldExpired(f"booking {booking_id} hold expired and slot was taken") from exc
    if booking.status != BookingStatus.HELD:
        raise IllegalTransition(f"cannot confirm booking in status {booking.status}")

    with conn.cursor() as cur:
        cur.execute(
            "UPDATE bookings SET status = 'confirmed', hold_expires_at = NULL WHERE id = %s",
            (booking_id,),
        )
    write_audit(
        conn,
        actor_staff_id=None,
        action="booking.confirm",
        entity="bookings",
        entity_id=booking_id,
        detail={"paybridge_payment_id": paybridge_payment_id},
    )
    enqueue(conn, template="booking_confirmed", booking_id=booking_id)

    # Close off the waitlist entry if this hold was a waitlist offer.
    from hallpass.bookings.waitlist import on_booking_confirmed

    on_booking_confirmed(conn, booking_id)

    booking.status = BookingStatus.CONFIRMED
    booking.hold_expires_at = None
    return booking


def _revive_expired_hold(conn: Connection, booking: Booking) -> Booking:
    try:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE bookings
                       SET status = 'confirmed', cancelled_at = NULL, cancel_reason = NULL,
                           hold_expires_at = NULL
                     WHERE id = %s
                    """,
                    (booking.id,),
                )
    except errors.ExclusionViolation as exc:
        raise BookingConflict(
            "slot taken after hold expired",
            space_id=booking.space_id,
            starts_at=booking.starts_at,
            ends_at=booking.ends_at,
        ) from exc
    log.info("revived expired hold %s after late payment", booking.id)
    enqueue(conn, template="booking_confirmed", booking_id=booking.id)
    booking.status = BookingStatus.CONFIRMED
    booking.cancelled_at = None
    booking.cancel_reason = None
    return booking


def cancel(
    conn: Connection,
    booking_id: int,
    *,
    reason: str,
    by_staff_id: int | None = None,
    notify: bool = True,
    promote_waitlist: bool = True,
) -> Booking:
    """Cancel (a.k.a. withdraw) a booking.

    Refund calculation is billing's job (ADR 0012, tiered by notice). We flip
    the status and call ``refund_requested`` in the same transaction.
    ``reason`` is free text-ish, but these values are special: 'customer',
    'staff', 'closure' (full refund whatever the notice) and 'hold_expired'
    (nothing to refund). The staff screen lets people type other things;
    billing treats anything that isn't 'closure' as a normal cancellation.
    """
    booking = get_booking(conn, booking_id, for_update=True)
    if booking.status == BookingStatus.CANCELLED:
        return booking
    if booking.status == BookingStatus.NO_SHOW:
        raise IllegalTransition("can't cancel a no-show")

    now = now_utc()
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE bookings
               SET status = 'cancelled', cancelled_at = %(now)s, cancel_reason = %(reason)s
             WHERE id = %(id)s
            """,
            {"now": now, "reason": reason, "id": booking_id},
        )
    write_audit(
        conn,
        actor_staff_id=by_staff_id,
        action="booking.cancel",
        entity="bookings",
        entity_id=booking_id,
        detail={"reason": reason, "was": str(booking.status)},
    )

    was_confirmed = booking.status == BookingStatus.CONFIRMED
    booking.status = BookingStatus.CANCELLED
    booking.cancelled_at = now
    booking.cancel_reason = reason

    if was_confirmed and reason != HOLD_EXPIRED:
        from hallpass.billing.refunds import refund_requested

        refund_requested(conn, booking=booking, full_refund=(reason == CLOSURE))

    if notify and reason != HOLD_EXPIRED:
        # Same template for closures; it shows the reason. Notifications
        # works out who to send it to (resident, or the org's contact).
        enqueue(conn, template="booking_cancelled", booking_id=booking_id)

    if promote_waitlist and booking.starts_at > now:
        # Inline promotion so the first person in the queue hears quickly.
        # NOTE: jobs.sweep_waitlist ALSO does this every 5 minutes. The two
        # can race -- see docs/known-issues/bookings.md (HP-541).
        from hallpass.bookings.waitlist import promote_for_slot

        promote_for_slot(conn, booking.space_id, booking.starts_at, booking.ends_at)

    return booking


def mark_no_show(conn: Connection, booking_id: int, *, staff_id: int) -> Booking:
    booking = get_booking(conn, booking_id, for_update=True)
    now = now_utc()
    if booking.status != BookingStatus.CONFIRMED:
        raise IllegalTransition(f"only confirmed bookings can be no-shows (this one is {booking.status})")
    if now < booking.starts_at + NO_SHOW_GRACE:
        raise IllegalTransition("too early to mark as no-show")
    if now > booking.starts_at + NO_SHOW_WINDOW:
        raise IllegalTransition("too late to mark as no-show; raise it with the facility manager")

    with conn.cursor() as cur:
        cur.execute("UPDATE bookings SET status = 'no_show' WHERE id = %s", (booking_id,))
    write_audit(conn, actor_staff_id=staff_id, action="booking.no_show", entity="bookings", entity_id=booking_id)
    booking.status = BookingStatus.NO_SHOW
    # No refund for no-shows. 3 in 12 weeks flags the resident on the staff
    # screen (accounts does that, not us). No automatic suspension.
    return booking
