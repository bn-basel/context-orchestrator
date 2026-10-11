---
kind: doc
status: verified
---

# Paybridge webhooks — design notes

Last reworked Nov 2024 (hotfix 2.6.1, which never made it into the changelog) after
the duplicate-delivery investigation.
Code: `billing/webhooks.py`, route in `api/payments.py`.

## What Paybridge sends us

| Event | What we do |
|---|---|
| `payment.succeeded` | payment → succeeded, confirm the hold (or revive it, or auto-refund) |
| `payment.failed` | payment → failed (+ `failure_code`); hold stays until it expires |
| `checkout.session.expired` | payment → expired (only if still pending) |
| `refund.succeeded` | refund → succeeded, payment → refunded / partially_refunded, email |
| `refund.failed` | refund → failed, shows in Finance's daily exceptions |
| `payment.disputed` | stored, nothing else. Finance handle chargebacks in Paybridge. |
| anything else | stored, marked processed, ignored |

Signature: header `Paybridge-Signature: t=<unix>,v1=<hex>[,v1=<hex>]`,
HMAC-SHA256 of `"<t>." + raw body`. We reject timestamps more than 5
minutes off. `HALLPASS_PAYBRIDGE_WEBHOOK_SECRET` can hold two secrets,
comma-separated, for rotation. **Add the new secret on our side first,
then rotate in the Paybridge dashboard, then remove the old one.**

## Delivery is at-least-once, and then some

Things we have actually seen:

1. **Retries.** No 2xx within 10s → retry with backoff for 72h. Same event id.
2. **Doubles.** The same event id twice within a second or two, even after
   we've answered 200. A few times a week. Probably their side retrying a
   request whose response they lost.
3. **Resends with new ids.** The dashboard "Resend" button and support's
   redelivery tool create a *new* event id for the same payment.
4. **Out of order.** `checkout.session.expired` after `payment.succeeded`
   for the same session, when the customer paid in the last few seconds.

## How we cope

- `paybridge_events.event_id` is unique. We upsert:
  `INSERT ... ON CONFLICT (event_id) DO UPDATE ... RETURNING processed_at`.
  The `DO UPDATE` takes a row lock, so a concurrent double waits for the
  first request's transaction to finish and then sees `processed_at` set →
  `duplicate`. That handles (1) and (2).
- If `processed_at` is still NULL (first attempt failed), we process again.
  This is the bit that was broken before Nov 2024.
- The handler runs inside a savepoint. If it throws, the event row survives
  with `error` filled in and the API still answers 200. The
  `process_paybridge_backlog` job retries unprocessed events every 5 minutes
  for up to 72 hours. We'd rather retry on our schedule than Paybridge's.
- (3) can't be caught by event id. Handlers are idempotent instead:
  `mark_succeeded` only updates rows in pending/failed/expired, and treats
  succeeded/refunded rows as "already done"; `mark_refund_settled` only
  touches requested/submitted refunds.
- (4): status guards again. `expire_checkout` only touches `pending`.
- `create_refund_row` caps at the refundable remainder, so a duplicate
  "paid after hold expired" can't produce a second refund.

## Things that are still not great

- `payment.succeeded` occasionally beats our own `INSERT INTO payments`
  (the session is created, Apple Pay completes in under a second, webhook
  arrives before our transaction commits). The handler raises
  `UnknownPayment`, the event is kept, and the backlog picks it up 5 minutes
  later. Customer sees "checking your payment…" for 5 minutes. Could be
  smarter.
- Events that are genuinely unknown (payments from the test-mode link that
  briefly went live in 2024, or for a payment we can't match) retry for 72h
  and then sit unprocessed forever. They're harmless but noisy.
- The runbook mentions `signature_ok = false` rows. The API rejects bad
  signatures with 403 *before* calling billing, so those rows never get
  written. Storing them would need care: if we stored the event id of an
  unverified request, a forged event could block the real one as a
  "duplicate". Left as is.
- No unique constraint stops two `payments` rows for one booking both being
  `succeeded` (two tabs, two checkouts, both paid). Rare. Reconciliation
  doesn't catch it either, since both are real Paybridge payments; it shows
  up as a complaint.
