"""Waitlist for fully booked slots.

A resident who can't get the slot they want can join the waitlist for that
space + time range. When a matching booking is cancelled (or a hold lapses)
the first person in the queue is *offered* the slot: we place a hold in
their name and send them an email/SMS with a link to pay. If they don't pay
within OFFER_TTL the hold is released and the next person gets it.

Behind the ``waitlist`` feature flag (per facility; it started as a pilot at
Eastfield in 2.2.0).

waitlist_entries.status:
    waiting   -> in the queue
    offered   -> we've placed a hold for them (offer_booking_id set)
    accepted  -> they paid; booking confirmed
    lapsed    -> offer ran out
    withdrawn -> they took themselves off
    expired   -> the slot is in the past now

(``position`` is a leftover from the first version, unused since 0010.)

Promotion happens in two places:
  1. inline from lifecycle.cancel() so it's quick
  2. jobs.sweep_waitlist() every 5 min, which catches lapsed offers and
     expired holds

!! These two can run at the same time and both pick the same "first waiting"
!! entry (HP-541). See the long comment in promote_for_slot and
!! docs/known-issues/bookings.md. Not fixed yet.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from psycopg import Connection
from psycopg.rows import dict_row

from hallpass.bookings import lifecycle
from hallpass.bookings.models import BookingConflict
from hallpass.core.clock import now_utc
from hallpass.core.errors import ValidationError
from hallpass.notifications.outbox import enqueue

log = logging.getLogger(__name__)

# How long a waitlisted person has to pay once offered. Longer than a normal
# hold because they might not see the email straight away.
OFFER_TTL = timedelta(hours=2)

# Don't offer slots starting within this window; nobody will make it.
MIN_NOTICE_FOR_OFFER = timedelta(hours=3)

MAX_ENTRIES_PER_RESIDENT = 5


def join(
    conn: Connection, *, resident_id: int, space_id: int, starts_at: datetime, ends_at: datetime
) -> int:
    if ends_at <= starts_at or starts_at <= now_utc():
        raise ValidationError("that time can't be waited for")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM waitlist_entries WHERE resident_id = %s AND status IN ('waiting', 'offered')",
            (resident_id,),
        )
        (n,) = cur.fetchone()  # type: ignore[misc]
        if n >= MAX_ENTRIES_PER_RESIDENT:
            raise ValidationError(f"you can be on at most {MAX_ENTRIES_PER_RESIDENT} waiting lists at once")

        cur.execute(
            """
            INSERT INTO waitlist_entries (resident_id, space_id, starts_at, ends_at, status, created_at)
            VALUES (%s, %s, %s, %s, 'waiting', %s)
            ON CONFLICT (resident_id, space_id, starts_at) WHERE status = 'waiting' DO NOTHING
            RETURNING id
            """,
            (resident_id, space_id, starts_at, ends_at, now_utc()),
        )
        row = cur.fetchone()
        if row is None:
            # already on it -- return the existing entry id
            cur.execute(
                "SELECT id FROM waitlist_entries WHERE resident_id = %s AND space_id = %s "
                "AND starts_at = %s AND status = 'waiting'",
                (resident_id, space_id, starts_at),
            )
            row = cur.fetchone()
    assert row is not None
    return row[0]


def withdraw(conn: Connection, entry_id: int, resident_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE waitlist_entries SET status = 'withdrawn', updated_at = %s
            WHERE id = %s AND resident_id = %s AND status = 'waiting'
            """,
            (now_utc(), entry_id, resident_id),
        )


def _next_candidate(conn: Connection, space_id: int, starts_at: datetime, ends_at: datetime) -> dict | None:
    # The entry's requested range has to fit inside the freed range. Someone
    # waiting for 19:00-21:00 doesn't get offered a freed 19:00-20:00.
    #
    # FIXME(HP-541): no row lock here. Should be FOR UPDATE SKIP LOCKED, and
    # really we want one promoter per space -- an advisory lock on space_id
    # was suggested (core.db.advisory_lock exists). See known-issues.
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT * FROM waitlist_entries
            WHERE space_id = %s
              AND status = 'waiting'
              AND starts_at >= %s AND ends_at <= %s
            ORDER BY created_at, id
            LIMIT 1
            """,
            (space_id, starts_at, ends_at),
        )
        return cur.fetchone()


def promote_for_slot(conn: Connection, space_id: int, starts_at: datetime, ends_at: datetime) -> int | None:
    """Offer a freed range to the next person in the queue. Returns the
    waitlist entry id that was offered, or None.

    HP-541, the race, step by step. A and B both call this for the same freed
    slot at the same moment (inline cancel + sweep job). Both read entry E.
      - A marks E offered, queues the offer to E, places the hold, commits.
      - B's UPDATE of E was waiting on A's row lock; it goes through, and B
        queues a *second* offer to E. B's place_hold fails (A's hold), so B
        resets E to 'waiting' -- undoing A's offer -- and moves on to entry F:
        marks it offered, queues an offer to F, place_hold fails again, resets
        F. B commits, and its queued messages go out with it.
    Net result: E gets two offer emails and has a real hold but an entry that
    says 'waiting' (so paying doesn't close it off); F gets an offer for a slot
    that's actually E's, and checkout tells F it's unavailable.
    """
    now = now_utc()
    if starts_at - now < MIN_NOTICE_FOR_OFFER:
        return None

    for _attempt in range(3):
        entry = _next_candidate(conn, space_id, starts_at, ends_at)
        if entry is None:
            return None

        # Mark first, tell them, then hold. (Yes, backwards. It was done this
        # way so the entry can't be offered twice by the same process if
        # place_hold is slow, and so the message goes out "as soon as
        # possible". It doesn't stop a *second* process. HP-541.)
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE waitlist_entries SET status = 'offered', offered_at = %s, updated_at = %s WHERE id = %s",
                (now, now, entry["id"]),
            )
        enqueue(conn, template="waitlist_offer", waitlist_entry_id=entry["id"])

        try:
            hold = lifecycle.place_hold(
                conn,
                space_id=space_id,
                starts_at=entry["starts_at"],
                ends_at=entry["ends_at"],
                resident_id=entry["resident_id"],
                ttl=OFFER_TTL,
            )
        except BookingConflict:
            log.warning(
                "waitlist entry %s: slot taken before hold could be placed (space %s %s)",
                entry["id"], space_id, entry["starts_at"],
            )
            # Put them back in the queue and try the next one. The offer
            # message has already been queued though -- that's the bug.
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE waitlist_entries SET status = 'waiting', offered_at = NULL WHERE id = %s",
                    (entry["id"],),
                )
            continue

        with conn.cursor() as cur:
            cur.execute(
                "UPDATE waitlist_entries SET offer_booking_id = %s WHERE id = %s",
                (hold.id, entry["id"]),
            )
        return entry["id"]

    return None


def on_booking_confirmed(conn: Connection, booking_id: int) -> None:
    """Called from lifecycle.confirm so the waitlist entry is closed off."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE waitlist_entries SET status = 'accepted', updated_at = %s "
            "WHERE offer_booking_id = %s AND status = 'offered'",
            (now_utc(), booking_id),
        )


def lapse_offers(conn: Connection) -> list[tuple[int, datetime, datetime]]:
    """Mark offers whose hold has been released as lapsed. Returns the freed
    (space_id, starts_at, ends_at) so the caller can promote the next person."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE waitlist_entries w
               SET status = 'lapsed', updated_at = %(now)s
              FROM bookings b
             WHERE b.id = w.offer_booking_id
               AND w.status = 'offered'
               AND b.status = 'cancelled'
            RETURNING w.space_id, w.starts_at, w.ends_at
            """,
            {"now": now_utc()},
        )
        return list(cur.fetchall())


def expire_past_entries(conn: Connection) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE waitlist_entries SET status = 'expired', updated_at = %(now)s "
            "WHERE status = 'waiting' AND starts_at < %(now)s",
            {"now": now_utc()},
        )
        return cur.rowcount
