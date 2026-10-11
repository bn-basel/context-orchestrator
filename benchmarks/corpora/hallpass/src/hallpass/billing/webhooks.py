"""Paybridge webhook handling.

The route (hallpass.api.payments.paybridge_webhook) verifies the signature
with ``verify_signature`` and then calls ``handle_paybridge_event`` inside a
transaction. Keep it that way round: verification needs the *raw* bytes,
not Flask's parsed JSON.

Delivery semantics, as far as we've been able to work out (Paybridge's docs
are vague and support were vaguer):

* At-least-once. If we don't answer 2xx within 10 seconds they retry with
  backoff for 72 hours. Same ``event.id`` on each retry.
* The same event sometimes arrives twice within a second or two even when we
  answered 200 to the first. We see this a few times a week. Same event id,
  so the dedupe below catches it.
* The "Resend" button in the Paybridge dashboard creates a NEW event id for
  the same payment. Finance used it while chasing a missing booking in early
  2025. Event dedupe can't catch that; the handlers have to be idempotent
  (payments.mark_succeeded, refunds.mark_refund_settled both are).

Dedupe: ``paybridge_events.event_id`` is UNIQUE. We do
``INSERT ... ON CONFLICT (event_id) DO UPDATE ... RETURNING processed_at``.
The DO UPDATE (rather than DO NOTHING) matters: it takes the row lock, so a
concurrent duplicate waits for the first transaction, and then we can tell
"already processed" (skip) from "stored but processing failed" (try again).

History: until 2.6.1 (Nov 2024) we did a plain INSERT, caught UniqueViolation
and returned 200 for any duplicate. If processing had failed on the first
delivery, every retry was then thrown away as a "duplicate" and the payment
never got recorded. See docs/findings/billing-webhook-duplicates-2024-11.md.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import Callable, Mapping
from typing import Any

import structlog
from psycopg import Connection
from psycopg.rows import dict_row

from hallpass.billing import payments, refunds
from hallpass.core.config import get_settings

log = structlog.get_logger(__name__)

TOLERANCE_SECONDS = 300
# Events older than this that still fail are left for a human (and show up
# in the daily exceptions email). 72h matches Paybridge's own retry window.
BACKLOG_GIVE_UP_HOURS = 72

Handler = Callable[[Connection, dict[str, Any]], None]


def _secrets() -> list[str]:
    # Comma-separated so a rotation can run with old and new secrets at once.
    # Rotate here FIRST, then in the Paybridge dashboard. (Jan 2025: somebody
    # did it the other way round.)
    raw = get_settings().paybridge_webhook_secret
    return [s.strip() for s in raw.split(",") if s.strip()]


def _parse_signature_header(value: str) -> tuple[int, list[str]] | None:
    """'t=1712345678,v1=abc...,v1=def...' -> (timestamp, [sigs]).

    Paybridge sends two v1 values while *their* side of a rotation is in progress.
    """
    ts: int | None = None
    sigs: list[str] = []
    for part in value.split(","):
        key, _, val = part.strip().partition("=")
        if key == "t" and val.isdigit():
            ts = int(val)
        elif key == "v1":
            sigs.append(val)
    if ts is None or not sigs:
        return None
    return ts, sigs


def verify_signature(raw_body: bytes, header_value: str | None, *, secrets: list[str] | None = None, now: float | None = None) -> bool:
    if not header_value:
        return False
    parsed = _parse_signature_header(header_value)
    if parsed is None:
        return False
    ts, sigs = parsed
    now = time.time() if now is None else now
    if abs(now - ts) > TOLERANCE_SECONDS:
        return False
    signed_payload = f"{ts}.".encode() + raw_body
    for secret in secrets if secrets is not None else _secrets():
        expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
        if any(hmac.compare_digest(expected, s) for s in sigs):
            return True
    return False


def _on_payment_succeeded(conn: Connection, obj: dict[str, Any]) -> None:
    payments.mark_succeeded(conn, paybridge_payment_id=obj["id"], amount_pence=int(obj["amount"]))


def _on_payment_failed(conn: Connection, obj: dict[str, Any]) -> None:
    payments.mark_failed(conn, paybridge_payment_id=obj["id"], failure_code=obj.get("failure_code"))


def _on_checkout_expired(conn: Connection, obj: dict[str, Any]) -> None:
    payments.expire_checkout(conn, checkout_id=obj["id"])


def _on_refund_succeeded(conn: Connection, obj: dict[str, Any]) -> None:
    refunds.mark_refund_settled(conn, paybridge_refund_id=obj["id"], succeeded=True)


def _on_refund_failed(conn: Connection, obj: dict[str, Any]) -> None:
    refunds.mark_refund_settled(conn, paybridge_refund_id=obj["id"], succeeded=False, failure_reason=obj.get("failure_reason"))


HANDLERS: Mapping[str, Handler] = {
    "payment.succeeded": _on_payment_succeeded,
    "payment.failed": _on_payment_failed,
    "checkout.session.expired": _on_checkout_expired,
    "refund.succeeded": _on_refund_succeeded,
    "refund.failed": _on_refund_failed,
    # "payment.disputed" (chargebacks): maybe two a year. Finance handle them
    # in the Paybridge dashboard. We store the event and do nothing.
}


def _dispatch(conn: Connection, row_id: int, event: dict[str, Any]) -> str:
    handler = HANDLERS.get(event["type"])
    if handler is None:
        conn.execute("UPDATE paybridge_events SET processed_at = now(), error = NULL WHERE id = %s", (row_id,))
        return "ignored"
    try:
        with conn.transaction():  # savepoint: a failing handler must not lose the stored event
            handler(conn, event["data"]["object"])
    except Exception as exc:
        log.warning("paybridge.event_failed", event_id=event["id"], event_type=event["type"], error=repr(exc))
        conn.execute("UPDATE paybridge_events SET error = %s WHERE id = %s", (repr(exc)[:1000], row_id))
        return "failed"
    conn.execute("UPDATE paybridge_events SET processed_at = now(), error = NULL WHERE id = %s", (row_id,))
    return "processed"


def handle_paybridge_event(conn: Connection, *, raw_body: bytes) -> str:
    """Store and process one (already signature-checked) delivery.

    Returns 'processed', 'duplicate', 'ignored' or 'failed'. The API answers
    200 for all of them: a 'failed' event is stored with its error and the
    backlog job retries it every 5 minutes, which is more predictable than
    leaning on Paybridge's retry schedule.
    """
    event = json.loads(raw_body)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO paybridge_events (event_id, event_type, payload, signature_ok)
            VALUES (%s, %s, %s, true)
            ON CONFLICT (event_id) DO UPDATE SET event_type = EXCLUDED.event_type
            RETURNING id, processed_at
            """,
            (event["id"], event["type"], json.dumps(event)),
        )
        row = cur.fetchone()
    assert row is not None
    if row["processed_at"] is not None:
        log.info("paybridge.duplicate", event_id=event["id"], event_type=event["type"])
        return "duplicate"
    return _dispatch(conn, row["id"], event)


def process_unprocessed_events(conn: Connection, *, limit: int = 500, dry_run: bool = False) -> int:
    """Worker job (*/5). Retry stored events that haven't been processed.

    SKIP LOCKED so a live webhook delivery for the same event (which holds the
    row lock) is simply passed over this time round.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT id, payload
              FROM paybridge_events
             WHERE processed_at IS NULL
               AND signature_ok
               AND received_at < now() - interval '1 minute'
               AND received_at > now() - make_interval(hours => %s)
             ORDER BY received_at
             LIMIT %s
             FOR UPDATE SKIP LOCKED
            """,
            (BACKLOG_GIVE_UP_HOURS, limit),
        )
        rows = cur.fetchall()
    if dry_run:
        return len(rows)
    done = 0
    for r in rows:
        if _dispatch(conn, r["id"], r["payload"]) != "failed":
            done += 1
    return done
