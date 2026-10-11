"""Transactional outbox (ADR 0008).

Domain code calls enqueue() inside its own transaction, passing a template
name and whatever id it has:

    enqueue(conn, template="booking_cancelled", booking_id=b.id)
    enqueue(conn, template="refund_issued", refund_id=r_id)

enqueue works out who to tell and on which channel(s) and writes one
notifications_outbox row per message. The worker's dispatch_outbox job
(every minute) calls dispatch_pending().

Row lifecycle: pending -> sending -> sent | pending (retry) | failed | dead.

Claiming commits status='sending' before we talk to SMTP/TextHub, so no DB
transaction is held across a network call. Delivery is therefore at-least-
once: a send that succeeds but isn't recorded (read timeout, worker killed,
reaper firing on a slow send) is sent again. For SMS that means duplicate
texts - see docs/known-issues/accounts-and-notifications.md.

There's no claimed_at column, so while a row is 'sending' we reuse
not_before as the claim time. Ugly; saves a migration.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from hallpass.notifications import recipients
from hallpass.core import clock

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 6
BACKOFF = timedelta(minutes=1)  # 1, 2, 4, 8, 16 min, then dead
STUCK_AFTER = timedelta(minutes=10)

# Login links go first so a burst of reminders can't hold up someone logging in.
_CLAIM_ORDER = "CASE WHEN template IN ('magic_link', 'staff_magic_link') THEN 0 ELSE 1 END, not_before, id"


class TransientSendError(Exception):
    """Retry: timeouts, 5xx, SMTP 4xx, connection refused."""


class PermanentSendError(Exception):
    """Don't retry: bad number, hard bounce, missing template, opted out."""


def enqueue(conn, *, template: str, not_before: datetime | None = None,
            context: dict | None = None, to_email: str | None = None, allow_sms: bool = True,
            **refs: int) -> list[int]:
    """Queue a notification. Returns the new outbox ids (can be empty, e.g.
    an anonymised resident).

    refs: booking_id, series_id, waitlist_entry_id, refund_id, invoice_id or
    resident_id (first one found wins); extras like blackout_id just ride
    along in the context. to_email is for people without a resident row
    (staff login links). allow_sms only matters for booking_reminder.
    """
    messages = recipients.resolve(conn, template, refs, to_email=to_email, allow_sms=allow_sms)
    ids = []
    for msg in messages:
        row = conn.execute(
            """
            INSERT INTO notifications_outbox
                (channel, recipient, template, context, resident_id, booking_id, not_before)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
            """,
            (msg.channel, msg.recipient, template, json.dumps({**msg.context, **(context or {})}),
             msg.resident_id, msg.booking_id, not_before or clock.now()),
        ).fetchone()
        ids.append(row[0])
    if not messages:
        log.info("enqueue %s %s: nobody to notify", template, refs)
    return ids


def _claim(conn, batch_size: int) -> list[tuple]:
    now = clock.now()
    with conn.transaction():
        return conn.execute(
            f"""
            UPDATE notifications_outbox SET status = 'sending', not_before = %(now)s
            WHERE id IN (
                SELECT id FROM notifications_outbox
                WHERE status = 'pending' AND not_before <= %(now)s
                ORDER BY {_CLAIM_ORDER}
                LIMIT %(n)s FOR UPDATE SKIP LOCKED)
            RETURNING id, channel, recipient, template, context, attempts
            """,
            {"now": now, "n": batch_size},
        ).fetchall()


def _reap_stuck(conn) -> int:
    """Rows 'sending' for > 10 minutes go back to pending. Added after the
    worker was OOM-killed in 2023 and left rows stuck forever. Also a source
    of duplicates when a batch is merely slow (TextHub timeouts x 200 rows)."""
    with conn.transaction():
        return conn.execute(
            "UPDATE notifications_outbox SET status = 'pending', attempts = attempts + 1, "
            "last_error = 'reaped from sending' WHERE status = 'sending' AND not_before < %s",
            (clock.now() - STUCK_AFTER,),
        ).rowcount


def _retry(conn, row_id: int, attempts: int, error: str) -> None:
    attempts += 1
    if attempts >= MAX_ATTEMPTS:
        conn.execute("UPDATE notifications_outbox SET status = 'dead', attempts = %s, last_error = %s "
                     "WHERE id = %s", (attempts, error[:1000], row_id))
        log.error("outbox %s dead after %s attempts", row_id, attempts)
        return
    conn.execute(
        "UPDATE notifications_outbox SET status = 'pending', attempts = %s, not_before = %s, "
        "last_error = %s WHERE id = %s",
        (attempts, clock.now() + BACKOFF * 2 ** (attempts - 1), error[:1000], row_id),
    )


def dispatch_pending(conn, *, batch_size: int = 200, dry_run: bool = False,
                     email_sender=None, sms_sender=None) -> int:
    from hallpass.notifications.email_sender import default_email_sender
    from hallpass.notifications.sms_sender import TextHubSender

    if dry_run:
        (n,) = conn.execute("SELECT count(*) FROM notifications_outbox WHERE status = 'pending' "
                            "AND not_before <= %s", (clock.now(),)).fetchone()
        return n
    email_sender = email_sender or default_email_sender()
    sms_sender = sms_sender or TextHubSender()
    _reap_stuck(conn)
    rows = _claim(conn, batch_size)
    for row_id, channel, recipient, template, ctx, attempts in rows:
        sender = sms_sender if channel == "sms" else email_sender
        try:
            sender.send(row_id=row_id, recipient=recipient, template=template, context=ctx)
        except PermanentSendError as exc:
            with conn.transaction():
                conn.execute("UPDATE notifications_outbox SET status = 'failed', last_error = %s "
                             "WHERE id = %s", (str(exc)[:1000], row_id))
            continue
        except Exception as exc:  # noqa: BLE001 - TransientSendError and anything unexpected
            with conn.transaction():
                _retry(conn, row_id, attempts, repr(exc))
            continue
        with conn.transaction():
            conn.execute("UPDATE notifications_outbox SET status = 'sent', sent_at = %s, last_error = NULL "
                         "WHERE id = %s", (clock.now(), row_id))
    return len(rows)
