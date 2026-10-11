# Manual refunds and stuck refunds

For developers on support rota and for Finance users of the back office.

## Who can refund what

- **Automatic** refunds happen when a booking is cancelled (ADR 0012 tiers),
  when the council closes a space, and when a payment arrives after the
  hold expired and someone else got the slot (`hold_expired_before_payment`).
  Nobody has to do anything.
- **Discretionary** refunds (illness, complaint, "the heating was off") are
  for the `finance` role only (`issue_refund` permission). Facility staff
  can't, and that's deliberate — see `docs/accounts/roles.md`.

## Doing a discretionary refund

Back office → Payments → find the payment (search by booking number, email,
or the `pay_...` id from Paybridge) → **Refund**.

- Amount can be anything up to what's left on the payment. If a booking was
  already 50% refunded on cancellation, you can top it up to 100%.
- Reason is mandatory and ends up in the audit log and in the refund email
  wording, so write something you'd be happy for the resident to read.
- The refund is created as `requested`. The `submit_refunds` job sends it to
  Paybridge within 5 minutes; `succeeded` arrives by webhook, usually within
  a minute after that. The resident's bank takes 3-5 working days.

**Don't refund in the Paybridge dashboard.** We don't track dashboard
refunds; the payment stays `succeeded` here, the income report is wrong,
and reconciliation flags it as `refund_unknown` every night until someone
cleans it up. If you've already done it, tell a developer.

## Organisations on invoice

There is nothing to refund — they haven't paid by card. Options:

- Invoice not issued yet: cancel the booking with reason `closure` (if it's
  our fault) and no line will appear.
- Invoice issued, not paid: void it in the back office and re-run invoicing
  for that month (Back office → Invoices → Run). The re-run only picks up
  bookings not on a live invoice.
- Invoice already paid: we don't do credit notes in Hallpass. Finance raise
  one in the finance system. Yes, it's a gap.

## Stuck refunds

Symptoms: refund sits in `requested` or `submitted` for more than an hour.

`requested` for ages:
- Is the worker running? (`systemctl status hallpass-worker.timer` on hp-app-01)
- Check logs for `refund.submit_failed`. Common causes: Paybridge down,
  API key expired, or the payment was already fully refunded in the
  dashboard (Paybridge returns 400 `amount_exceeds_refundable`). In that
  last case mark our refund `failed` by hand with a note and fix the
  payment status.

`submitted` for ages:
- The `refund.succeeded` webhook didn't arrive or didn't verify. Look in
  `paybridge_events` for the `re_...` id. If it's missing entirely, ask
  Paybridge support to redeliver (by event id or time range). If it's there
  with an `error`, the backlog job will keep retrying for 72h; read the error.
- January 2025: 11 refunds stuck in `submitted` for weeks because the
  webhook secret was rotated on Paybridge's side without updating ours, and
  the fix landed after Paybridge's 72h retry window. The reconciliation
  audit found them. See `docs/findings/billing-reconciliation-audit-2025-03.md`.
  Reconciliation now flags this as `refund_stuck`.

Fixing a stuck `submitted` refund by hand once you've confirmed in the
Paybridge dashboard that it really succeeded:

```sql
BEGIN;
UPDATE refunds SET status = 'succeeded' WHERE id = :id AND status = 'submitted';
-- then fix the payment status: 'refunded' if nothing left, else 'partially_refunded'
COMMIT;
```

and add an audit_log note. Better: redeliver the webhook and let the code do it.

## Retrying failed refunds

Don't press Retry on a refund that failed more than 24 hours ago without
checking Paybridge first. Our idempotency key only protects against double
refunds inside Paybridge's 24-hour window.
