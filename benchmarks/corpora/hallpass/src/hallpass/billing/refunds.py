"""Refunds (card) and the refund policy.

Policy is ADR 0012 ("v2, tiered by notice period"), which replaced ADR 0007
(full refund up to 24h before, nothing after) in release 2.1.0, Feb 2024:

    notice >= 7 days           100%
    48 hours <= notice < 7d     50%
    notice < 48 hours            0%
    council closure            100% regardless of notice
    paid after hold expired    100% (see payments.mark_succeeded)
    manual (finance role)      any amount up to what's left on the payment

"Notice" is ``starts_at - cancelled_at`` in real elapsed time (both UTC).
So "7 days" is 168 hours, which is not the same as "the same time a week
earlier" across a clock change. Known issue, low priority.

v1 is still here behind the ``refund_policy_v2`` flag (ADR 0014). The flag
was added already-on in migration 0009 (April 2024) as a fallback for
Finance and has never been turned off. TODO: delete v1 and the flag. Keeps
not happening because nobody wants to be the one who removed the safety net.

Organisations on invoice don't get refunds: cancelled bookings drop off the
next invoice and any cancellation charge becomes a line (invoices.py).

refunds.status: requested -> submitted -> succeeded | failed.
refunds.policy_tier (since 3.2) records which rule produced the amount;
NULL for anything older.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime, timedelta

import structlog
from psycopg import Connection
from psycopg.rows import dict_row

from hallpass.billing.errors import AlreadyRefunded, PaybridgeError, RefundNotAllowed
from hallpass.billing.paybridge import PaybridgeClient
from hallpass.bookings.models import Booking
from hallpass.core import clock, flags
from hallpass.core.audit import write_audit
from hallpass.core.money import format_gbp, percent_of
from hallpass.notifications.outbox import enqueue

log = structlog.get_logger(__name__)

FULL_NOTICE = timedelta(days=7)
PARTIAL_NOTICE = timedelta(hours=48)
PARTIAL_PERCENT = 50

V1_NOTICE = timedelta(hours=24)  # ADR 0007, superseded


class Tier(enum.StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    NONE = "none"
    CLOSURE = "closure"
    V1_FULL = "v1_full"
    V1_NONE = "v1_none"


@dataclass(frozen=True, slots=True)
class RefundDecision:
    tier: Tier
    amount_pence: int
    notice: timedelta


def decide(
    price_pence: int,
    starts_at: datetime,
    cancelled_at: datetime,
    *,
    closure: bool = False,
    use_v2: bool = True,
) -> RefundDecision:
    """Pure policy function. No DB, no flags -- easy to test."""
    notice = starts_at - cancelled_at
    if closure:
        return RefundDecision(Tier.CLOSURE, price_pence, notice)
    if not use_v2:
        if notice >= V1_NOTICE:
            return RefundDecision(Tier.V1_FULL, price_pence, notice)
        return RefundDecision(Tier.V1_NONE, 0, notice)
    if notice >= FULL_NOTICE:
        return RefundDecision(Tier.FULL, price_pence, notice)
    if notice >= PARTIAL_NOTICE:
        # Half-up via core.money. Concessions round DOWN per slot, so on a
        # discounted odd amount this 50% can be a penny "generous". HP-412.
        return RefundDecision(Tier.PARTIAL, percent_of(price_pence, PARTIAL_PERCENT), notice)
    return RefundDecision(Tier.NONE, 0, notice)


def refundable_remaining(conn: Connection, payment_id: int) -> int:
    row = conn.execute(
        """
        SELECT p.amount_pence - COALESCE(SUM(r.amount_pence) FILTER (WHERE r.status <> 'failed'), 0)
          FROM payments p LEFT JOIN refunds r ON r.payment_id = p.id
         WHERE p.id = %s AND p.status IN ('succeeded', 'partially_refunded')
         GROUP BY p.id, p.amount_pence
        """,
        (payment_id,),
    ).fetchone()
    return int(row[0]) if row else 0


def create_refund_row(
    conn: Connection,
    *,
    payment_id: int,
    amount_pence: int,
    reason: str,
    policy_tier: str | None = None,
    staff_id: int | None = None,
) -> int | None:
    """Insert a 'requested' refund, capped at what's left on the payment.

    The cap is what stopped the double auto-refunds of 2024 from becoming
    real double refunds: the second one now gets capped to 0 and skipped.
    """
    amount = min(amount_pence, refundable_remaining(conn, payment_id))
    if amount <= 0:
        log.info("refund.nothing_left", payment_id=payment_id, reason=reason)
        return None
    row = conn.execute(
        """
        INSERT INTO refunds (payment_id, amount_pence, reason, status, policy_tier, requested_by)
        VALUES (%s, %s, %s, 'requested', %s, %s)
        RETURNING id
        """,
        (payment_id, amount, reason, policy_tier, staff_id),
    ).fetchone()
    assert row is not None
    return row[0]


def refund_requested(conn: Connection, *, booking: Booking, full_refund: bool = False) -> int | None:
    """Called by bookings.lifecycle.cancel() in the same transaction.

    Only writes the refunds row. The Paybridge call happens in the worker
    (``submit_requested_refunds``) so a Paybridge timeout can't roll back the
    cancellation itself.
    """
    if booking.resident_id is None:
        return None  # organisation on invoice; handled on the invoice
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT id FROM payments
             WHERE booking_id = %s AND method = 'card'
               AND status IN ('succeeded', 'partially_refunded')
             ORDER BY created_at DESC LIMIT 1
            """,
            (booking.id,),
        )
        payment = cur.fetchone()
    if payment is None:
        return None
    assert booking.cancelled_at is not None
    decision = decide(
        booking.price_pence,
        booking.starts_at,
        booking.cancelled_at,
        closure=full_refund,
        use_v2=flags.is_enabled("refund_policy_v2"),
    )
    if decision.amount_pence <= 0:
        log.info("refund.none_due", booking_id=booking.id, tier=decision.tier)
        return None
    return create_refund_row(
        conn,
        payment_id=payment["id"],
        amount_pence=decision.amount_pence,
        reason=booking.cancel_reason or "cancelled",
        policy_tier=decision.tier.value,
    )


def request_refund(conn: Connection, *, payment_id: int, amount_pence: int, reason: str, staff_id: int) -> dict:
    """Manual refund from the back office (finance/superuser, checked in the API)."""
    if amount_pence <= 0:
        raise RefundNotAllowed("amount must be positive")
    if not reason.strip():
        raise RefundNotAllowed("a reason is required for manual refunds")
    remaining = refundable_remaining(conn, payment_id)
    if remaining <= 0:
        raise AlreadyRefunded(f"payment {payment_id} has nothing left to refund")
    if amount_pence > remaining:
        raise RefundNotAllowed(f"only {format_gbp(remaining)} left to refund on this payment")
    refund_id = create_refund_row(
        conn, payment_id=payment_id, amount_pence=amount_pence, reason=reason.strip(), policy_tier="manual", staff_id=staff_id
    )
    write_audit(
        conn,
        actor_staff_id=staff_id,
        action="refund.manual",
        entity="refunds",
        entity_id=refund_id,
        detail={"payment_id": payment_id, "amount_pence": amount_pence, "reason": reason},
    )
    return {"id": refund_id, "payment_id": payment_id, "amount_pence": amount_pence, "status": "requested"}


def submit_requested_refunds(conn: Connection, client: PaybridgeClient | None = None, limit: int = 50) -> int:
    """Worker job ``submit_refunds`` (every 5 min, since 3.2). Sends
    'requested' refunds to Paybridge. Before 3.2 we called Paybridge inside
    the cancel request, and a Paybridge timeout rolled back the cancellation.

    Idempotency key is the refunds.id, so a retry within Paybridge's 24h
    window can't double-refund. After 24h it could: if a submit timed out on
    our side but actually went through on theirs, and nobody looks at it for
    a day, the next attempt would refund again. Hasn't happened (that we know of).
    """
    client = client or PaybridgeClient()
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT r.id, r.amount_pence, r.reason, p.paybridge_payment_id
              FROM refunds r JOIN payments p ON p.id = r.payment_id
             WHERE r.status = 'requested'
             ORDER BY r.created_at
             LIMIT %s
             FOR UPDATE OF r SKIP LOCKED
            """,
            (limit,),
        )
        rows = cur.fetchall()
    sent = 0
    for r in rows:
        try:
            resp = client.create_refund(
                payment_id=r["paybridge_payment_id"],
                amount_pence=r["amount_pence"],
                idempotency_key=f"refund:{r['id']}",
                note=r["reason"],
            )
        except PaybridgeError as exc:
            log.warning("refund.submit_failed", refund_id=r["id"], error=str(exc))
            continue
        conn.execute(
            "UPDATE refunds SET status = 'submitted', paybridge_refund_id = %s WHERE id = %s",
            (resp["id"], r["id"]),
        )
        sent += 1
    return sent


def mark_refund_settled(conn: Connection, *, paybridge_refund_id: str, succeeded: bool, failure_reason: str | None = None) -> None:
    """From the refund.succeeded / refund.failed webhooks. Idempotent."""
    status = "succeeded" if succeeded else "failed"
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            UPDATE refunds SET status = %s
             WHERE paybridge_refund_id = %s AND status IN ('requested', 'submitted')
            RETURNING id, payment_id, amount_pence
            """,
            (status, paybridge_refund_id),
        )
        row = cur.fetchone()
    if row is None:
        # Duplicate delivery, or a refund someone made directly in the Paybridge
        # dashboard (we don't track those -- please don't).
        return
    if not succeeded:
        log.error("refund.failed", refund_id=row["id"], reason=failure_reason)
        return
    left = refundable_remaining(conn, row["payment_id"])
    conn.execute(
        "UPDATE payments SET status = %s WHERE id = %s",
        ("refunded" if left <= 0 else "partially_refunded", row["payment_id"]),
    )
    _notify(conn, row["id"], row["payment_id"], row["amount_pence"])


def _notify(conn: Connection, refund_id: int, payment_id: int, amount_pence: int) -> None:
    who = conn.execute(
        """
        SELECT r.id, r.email, b.id FROM payments p
          JOIN bookings b ON b.id = p.booking_id
          JOIN residents r ON r.id = b.resident_id
         WHERE p.id = %s
        """,
        (payment_id,),
    ).fetchone()
    if who is None:
        return
    enqueue(
        conn,
        kind="refund_issued",
        channel="email",
        recipient=who[1],
        resident_id=who[0],
        booking_id=who[2],
        payload={"amount": format_gbp(amount_pence), "refund_id": refund_id},
        clock=clock,
        dedupe_key=f"refund_issued:{refund_id}",
    )


def refund_preview(price_pence: int, starts_at: datetime) -> RefundDecision:
    """What the 'Cancel booking' page shows before the hirer confirms.

    NB: always v2, ignores the flag. If anyone ever turns refund_policy_v2 off,
    the page and the actual refund will disagree.
    """
    return decide(price_pence, starts_at, clock.now(), use_v2=True)
