---
kind: finding
status: verified
---

# Investigation: duplicate Paybridge webhooks and lost payments (HP-430)

Tom Ellery, 28 Oct – 5 Nov 2024.

## Trigger

Two complaints in one week via the contact centre:

1. A resident was charged £36 for a hall booking that then showed as
   cancelled ("your hold has expired"). No refund.
2. A different resident got two "booking confirmed" emails a minute apart
   and asked whether they'd been charged twice. (They hadn't.)

## What I looked at

- `paybridge_events` for September and October 2024 (~9,800 events).
- Application logs for `UniqueViolation` on `paybridge_events_event_id_key`.
- The Paybridge dashboard's delivery log for both complaint payments.

## What was going on

**Duplicates are common.** 61 event ids in October were delivered more than
once (0.6%). 44 were Paybridge retries after a slow response from us (>10s;
these lined up with the 05:00 invoice run and with the Saturday morning
booking rush). 17 were two deliveries within ~2 seconds where we'd answered
200 to the first. Paybridge support confirmed the second kind "can occur"
and that we should be idempotent. Fair.

**The dedupe was wrong in a way that lost payments.** The handler did:

1. `INSERT INTO paybridge_events` in its own transaction, commit;
2. process the event in a second transaction;
3. on `UniqueViolation` in step 1, return 200 "duplicate".

If step 2 failed (complaint 1: lock timeout, because the hold expiry job
had the booking row locked), the event row existed with `processed_at` NULL.
Paybridge retried, step 1 hit the unique constraint, we said "duplicate",
and the payment was never recorded. The `process_paybridge_backlog` job
existed but only looked at events less than 10 minutes old, so it missed
these too (the hold expiry contention lasted longer than that on busy mornings).

**The double email** (complaint 2) was the "Resend" button. Someone in
Finance had resent the event from the dashboard while checking something;
it came with a new event id, so our dedupe didn't recognise it, and
`mark_succeeded` at the time didn't check the payment's current status
before calling `confirm` → second `booking_confirmed` email. Bookings'
`confirm` was already idempotent for the booking itself; the notification
wasn't.

## Changes (2.6.1, 5 Nov 2024)

- One transaction: upsert the event row
  (`ON CONFLICT (event_id) DO UPDATE ... RETURNING processed_at`), and only
  skip if it's already processed. The row lock makes concurrent doubles wait.
- Handler runs in a savepoint; on failure we keep the event with its
  `error` and return 200. Backlog job retries for 72h instead of 10 minutes.
- `mark_succeeded` only acts on pending/failed rows and treats an already
  succeeded payment as done.
- `confirm` no longer re-sends the email for an already confirmed booking
  (bookings team, same release).

## Verification

- Replayed October's 9,800 events against a restored copy with the new
  code, including every duplicate, in random order: no double state
  changes, no duplicate notifications.
- Two weeks after release: 23 duplicate deliveries, all answered
  "duplicate", 0 lost. 4 transient failures, all recovered by the backlog
  job within 10 minutes.

## Not fixed / follow-ups

- Payments lost *before* the fix: unknown how many. Recommended a full
  reconciliation against Paybridge (done in March 2025, found 9; see
  `billing-reconciliation-audit-2025-03.md`).
- Resent events for an already-*refunded* payment still fail (the guard
  only knows "succeeded"). Low priority. (Fixed in 3.1.0.)
- Duplicates of `payment.succeeded` for late payments can try to create two
  automatic refunds. Paybridge rejects the second one, so no money moves,
  but it leaves a `failed` refund behind. (Fixed later with the refundable
  cap in `create_refund_row`.)
