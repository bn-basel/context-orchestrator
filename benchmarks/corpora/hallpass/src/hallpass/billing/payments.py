"""Card payments via Paybridge hosted checkout.

Flow (resident paying by card):

1. bookings creates a `held` booking (hold length HALLPASS_HOLD_MINUTES,
   15 by default since v2.5.0).
2. ``start_checkout`` creates a Paybridge checkout session for
   bookings.price_pence and a `payments` row in status 'pending'. Since
   Paybridge API version 2024-02-01 the session comes back with its
   payment id already allocated, so we store paybridge_payment_id up front.
3. Paybridge calls our webhook with ``payment.succeeded`` (webhooks.py).
   ``mark_succeeded`` flips the payment to 'succeeded' and confirms the hold.
4. The browser lands on /api/payments/return. We do NOT confirm anything
   from the redirect; ``checkout_status`` just reports what we know so the
   page can poll.

Organisations on account never come through here; they get invoices.

payments.status: pending, succeeded, failed, expired, refunded,
partially_refunded. 'expired' only exists since 3.2 (migration 0010); older
abandoned checkouts are 'failed' with a NULL failure_code, so don't use
status to count card declines before June 2025. (refunded and
partially_refunded are maintained by refunds.py. Derived data, arguably
shouldn't be stored. They are.)
"""

from __future__ import annotations

from datetime import timedelta

import structlog
from psycopg import Connection
from psycopg.rows import dict_row

from hallpass.billing.errors import BillingError
from hallpass.billing.paybridge import PaybridgeClient
from hallpass.bookings import lifecycle
from hallpass.bookings.models import HoldExpired
from hallpass.core import clock
from hallpass.core.audit import write_audit
from hallpass.core.config import get_settings
from hallpass.core.errors import Forbidden, NotFound
from hallpass.core.money import format_gbp

log = structlog.get_logger(__name__)

# Paybridge's own floor for a checkout session is 5 minutes.
MIN_SESSION_SECONDS = 300


class UnknownPayment(BillingError):
    """A payment.succeeded for a paybridge id we have no row for.

    Raised (rather than swallowed) so the event stays unprocessed and the
    backlog job retries it -- the usual cause is the webhook overtaking our
    own INSERT from start_checkout by a few hundred ms.
    """


def _attempt_number(conn: Connection, booking_id: int) -> int:
    row = conn.execute("SELECT count(*) FROM payments WHERE booking_id = %s", (booking_id,)).fetchone()
    return (row[0] if row else 0) + 1


def start_checkout(conn: Connection, *, booking_id: int, resident_id: int, client: PaybridgeClient | None = None) -> dict:
    client = client or PaybridgeClient()
    settings = get_settings()
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT b.id, b.status, b.price_pence, b.resident_id, b.hold_expires_at,
                   s.name AS space_name, r.email
              FROM bookings b
              JOIN spaces s ON s.id = b.space_id
              JOIN residents r ON r.id = b.resident_id
             WHERE b.id = %s
             FOR UPDATE OF b
            """,
            (booking_id,),
        )
        booking = cur.fetchone()
    if booking is None:
        raise NotFound(f"booking {booking_id} not found")
    if booking["resident_id"] != resident_id:
        raise Forbidden("not your booking")
    if booking["status"] != "held":
        raise BillingError(f"booking {booking_id} is {booking['status']}, can't take payment", code="not_held")

    if booking["price_pence"] == 0:
        # 100% concession (CARER) or a staff comp. Skip Paybridge entirely.
        lifecycle.confirm(conn, booking_id)
        return {"redirect_url": None, "confirmed": True}

    # The session must not outlive the hold, or people pay for a slot that's
    # already been released. Paybridge won't go below 5 minutes, so the last
    # few minutes of a hold are a small window where that can still happen.
    remaining = int((booking["hold_expires_at"] - clock.now()).total_seconds())
    expires_in = max(remaining, MIN_SESSION_SECONDS)

    # Reference changes per attempt: Paybridge idempotency keys live 24h, and
    # reusing "HP-B123" handed people back their already-expired session
    # (HP-301, fixed v2.2.1).
    reference = f"HP-B{booking_id}-{_attempt_number(conn, booking_id)}"
    session = client.create_checkout_session(
        amount_pence=booking["price_pence"],
        reference=reference,
        description=f"{booking['space_name']} hire",
        customer_email=booking["email"],
        success_url=f"{settings.base_url}/api/payments/return?ref={reference}",
        cancel_url=f"{settings.base_url}/bookings/{booking_id}",
        expires_in_seconds=expires_in,
    )
    conn.execute(
        """
        INSERT INTO payments (booking_id, amount_pence, method, paybridge_payment_id,
                              paybridge_checkout_id, status)
        VALUES (%s, %s, 'card', %s, %s, 'pending')
        """,
        (booking_id, booking["price_pence"], session.payment_id, session.id),
    )
    log.info("checkout.started", booking_id=booking_id, reference=reference, amount=format_gbp(booking["price_pence"]))
    return {
        "redirect_url": session.url,
        "expires_at": (clock.now() + timedelta(seconds=expires_in)).isoformat(),
    }


def checkout_status(conn: Connection, *, paybridge_reference: str) -> dict:
    """For the return page to poll. Reference looks like HP-B<booking>-<attempt>."""
    try:
        booking_id = int(paybridge_reference.split("-")[1].lstrip("B"))
    except (IndexError, ValueError):
        raise NotFound("unknown reference") from None
    row = conn.execute("SELECT status FROM bookings WHERE id = %s", (booking_id,)).fetchone()
    if row is None:
        raise NotFound("unknown reference")
    return {"booking_id": booking_id, "booking_status": row[0]}


def mark_succeeded(conn: Connection, *, paybridge_payment_id: str, amount_pence: int) -> int:
    """Record a successful card payment. Returns payments.id.

    Must be safe to call more than once for the same payment: Paybridge
    delivers at-least-once, and the dashboard "Resend" button produces a new
    event id that the event-level dedupe can't recognise. The
    ``status = 'pending'`` guard is what actually protects us.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            UPDATE payments
               SET status = 'succeeded', amount_pence = %s, updated_at = now()
             WHERE paybridge_payment_id = %s AND status IN ('pending', 'failed', 'expired')
            RETURNING id, booking_id
            """,
            (amount_pence, paybridge_payment_id),
        )
        pay = cur.fetchone()
    if pay is None:
        existing = conn.execute(
            "SELECT id, status FROM payments WHERE paybridge_payment_id = %s", (paybridge_payment_id,)
        ).fetchone()
        if existing is not None and existing[1] in ("succeeded", "refunded", "partially_refunded"):
            # Duplicate. Before v3.1.0 we only accepted 'succeeded' here, so a
            # resent event for an already-refunded payment raised UnknownPayment
            # and sat in the backlog forever. A handful still do -- see known issues.
            log.info("payment.duplicate_success", paybridge_payment_id=paybridge_payment_id, status=existing[1])
            return existing[0]
        raise UnknownPayment(f"no payments row for {paybridge_payment_id}")

    try:
        lifecycle.confirm(conn, pay["booking_id"], paybridge_payment_id=paybridge_payment_id)
    except HoldExpired:
        # Paid after the hold lapsed and somebody else has the slot now.
        # Agreed in the May 2024 holds meeting: automatic full refund, reason
        # 'hold_expired_before_payment', apology email. If the slot was still
        # free, lifecycle.confirm revives the hold instead and we never get here.
        from hallpass.billing.refunds import create_refund_row

        create_refund_row(
            conn,
            payment_id=pay["id"],
            amount_pence=amount_pence,
            reason="hold_expired_before_payment",
            policy_tier="late_payment",
        )
        log.warning("payment.after_hold_expiry", payment_id=pay["id"], booking_id=pay["booking_id"])

    write_audit(
        conn,
        actor_staff_id=None,
        action="payment.succeeded",
        entity="payments",
        entity_id=pay["id"],
        detail={"paybridge_payment_id": paybridge_payment_id, "amount_pence": amount_pence},
    )
    return pay["id"]


def mark_failed(conn: Connection, *, paybridge_payment_id: str, failure_code: str | None = None) -> None:
    # Leave the booking held; the hold-expiry job releases it, and the
    # customer can try another card in the meantime (new attempt, new row).
    conn.execute(
        """
        UPDATE payments SET status = 'failed', failure_code = %s, updated_at = now()
         WHERE paybridge_payment_id = %s AND status = 'pending'
        """,
        (failure_code, paybridge_payment_id),
    )


def expire_checkout(conn: Connection, *, checkout_id: str) -> None:
    """checkout.session.expired. Only touches rows still pending: Paybridge
    does sometimes send this *after* payment.succeeded for the same session."""
    conn.execute(
        """
        UPDATE payments SET status = 'expired', updated_at = now()
         WHERE paybridge_checkout_id = %s AND status = 'pending'
        """,
        (checkout_id,),
    )
