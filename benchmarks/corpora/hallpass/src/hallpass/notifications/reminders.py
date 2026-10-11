"""Day-before booking reminders. Worker job `queue_reminders`, hourly.

Finds confirmed bookings starting *tomorrow* (Europe/London date - this was
UTC once and bookings at 00:30 BST got reminded a day late) that haven't had
a reminder queued, and enqueues template 'booking_reminder' for each.
recipients.py picks SMS or email.

Marks bookings.reminder_queued_at in the same transaction, so a rerun or
overlapping run doesn't queue twice. (That stops double *queueing*. It does
nothing about double *sending* - that's the outbox retry problem.)

bookings.jobs.send_reminders is an older copy of this that predates the
notifications package. It's not in the crontab. It also doesn't pass
allow_sms, so if anyone wires it up it will ignore the sms_reminders kill
switch. Delete it when someone's in there.

SMS quiet hours: we don't send texts 21:00-08:00 London time. Reminders that
would go in quiet hours get not_before = 08:00. Since this runs hourly the
evening runs (21:00-23:00) push their texts to the next morning, which for
the next day's bookings is fine; for an 08:00 booking it means the text
arrives on the morning itself. Nobody has complained.
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta

from hallpass.core import tz
from hallpass.notifications import outbox

log = logging.getLogger(__name__)

QUIET_START, QUIET_END = time(21, 0), time(8, 0)


def next_allowed_sms_time(at: datetime) -> datetime:
    local = tz.to_local(at)
    if QUIET_END <= local.time() < QUIET_START:
        return at
    day = local.date() if local.time() < QUIET_END else local.date() + timedelta(days=1)
    return tz.local_to_utc(day, QUIET_END)


def queue_reminders(conn, *, now: datetime, include_sms: bool, dry_run: bool = False) -> int:
    tomorrow = tz.to_local(now).date() + timedelta(days=1)
    start, end = tz.local_day_bounds(tomorrow)
    with conn.transaction():
        rows = conn.execute(
            """
            SELECT id FROM bookings
            WHERE status = 'confirmed' AND reminder_queued_at IS NULL
              AND starts_at >= %s AND starts_at < %s
            ORDER BY starts_at
            FOR UPDATE SKIP LOCKED
            """,
            (start, end),
        ).fetchall()
        if dry_run:
            return len(rows)
        send_at = next_allowed_sms_time(now)
        for (booking_id,) in rows:
            # not_before applies to the email too when it falls in quiet
            # hours. Nobody minds a reminder email at 8am instead of 10pm.
            outbox.enqueue(conn, template="booking_reminder", booking_id=booking_id,
                           allow_sms=include_sms, not_before=send_at)
            conn.execute("UPDATE bookings SET reminder_queued_at = %s WHERE id = %s", (now, booking_id))
    log.info("queued %s reminders for %s (sms=%s)", len(rows), tomorrow, include_sms)
    return len(rows)


def cancel_pending(conn, booking_id: int) -> None:
    """Bookings calls this on cancel. If the reminder already went, too late.
    reminder_queued_at stays set, so an un-cancelled booking never gets a
    new reminder. Rare; known."""
    conn.execute(
        "UPDATE notifications_outbox SET status = 'failed', last_error = 'booking cancelled' "
        "WHERE booking_id = %s AND template = 'booking_reminder' AND status = 'pending'",
        (booking_id,),
    )
