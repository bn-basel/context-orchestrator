"""Scheduled bookings jobs. Called by hallpass/worker.py:

    release_expired_holds   every minute
    sweep_waitlist          every 5 minutes
    expire_waitlist         hourly

(Reminders used to be here too; they moved to notifications/reminders.py.)

Each unit of work runs in its own savepoint so one bad row doesn't block the
rest.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from psycopg import Connection

from hallpass.bookings import lifecycle, waitlist
from hallpass.bookings.availability import facility_for_space
from hallpass.core import flags
from hallpass.core.clock import now_utc

log = logging.getLogger(__name__)

BATCH = 200


def release_expired_holds(conn: Connection) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id FROM bookings
            WHERE status = 'held' AND hold_expires_at < %s
            ORDER BY hold_expires_at
            LIMIT %s
            """,
            (now_utc(), BATCH),
        )
        ids = [r[0] for r in cur.fetchall()]

    released = 0
    for booking_id in ids:
        try:
            with conn.transaction():
                b = lifecycle.cancel(
                    conn,
                    booking_id,
                    reason=lifecycle.HOLD_EXPIRED,
                    notify=False,
                    # sweep_waitlist picks these up. Doing it here too made
                    # HP-541 noticeably worse (changed Jan 2025).
                    promote_waitlist=False,
                )
            if b.cancel_reason == lifecycle.HOLD_EXPIRED:
                released += 1
        except Exception:  # noqa: BLE001 - one bad row shouldn't stop the rest
            log.exception("could not release hold %s", booking_id)
    if released:
        log.info("released %d expired holds", released)
    return released


def sweep_waitlist(conn: Connection) -> int:
    """Offer freed slots to the next person. Returns offers made.

    Races with the inline promotion in lifecycle.cancel -- HP-541. The
    ``waitlist`` flag is per facility, so it's checked here per space (the
    worker only short-circuits when it's off everywhere).
    """
    with conn.transaction():
        freed = waitlist.lapse_offers(conn)

    # Also catch holds that expired without being a waitlist offer, and
    # cancellations where the inline promotion found nobody / failed:
    # anything cancelled in the last 10 minutes with someone waiting for it.
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT b.space_id, b.starts_at, b.ends_at
            FROM bookings b
            JOIN waitlist_entries w
              ON w.space_id = b.space_id AND w.status = 'waiting'
             AND w.starts_at >= b.starts_at AND w.ends_at <= b.ends_at
            WHERE b.status = 'cancelled'
              AND b.cancelled_at > %s
              AND b.starts_at > %s
            """,
            (now_utc() - timedelta(minutes=10), now_utc()),
        )
        freed.extend(cur.fetchall())

    enabled: dict[int, bool] = {}
    offered = 0
    for space_id, starts_at, ends_at in freed:
        if space_id not in enabled:
            enabled[space_id] = flags.is_enabled("waitlist", facility_id=facility_for_space(conn, space_id))
        if not enabled[space_id]:
            continue
        try:
            with conn.transaction():
                if waitlist.promote_for_slot(conn, space_id, starts_at, ends_at) is not None:
                    offered += 1
        except Exception:  # noqa: BLE001
            log.exception("waitlist promotion failed for space %s at %s", space_id, starts_at)
    return offered


def expire_waitlist(conn: Connection) -> int:
    with conn.transaction():
        return waitlist.expire_past_entries(conn)
