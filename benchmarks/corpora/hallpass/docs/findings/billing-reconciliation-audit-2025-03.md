---
kind: finding
status: verified
---

# Reconciliation audit: Paybridge vs Hallpass, Oct 2024 – Feb 2025

Priya and Marcus Doyle, 3–14 March 2025. Requested by Janet Morley (Finance)
after the year-end pre-close review found income in Hallpass and cash
received from Paybridge differing by more than the usual timing noise.

## Question

For every card payment and refund Paybridge settled between 1 October 2024
and 28 February 2025, does Hallpass have a matching record with the same
amount and the right status — and vice versa? And separately: does the
price we charged match what Finance would calculate from the tariff?

## Method

1. Exported Paybridge settlement reports for the five months (CSV from the
   dashboard; the API settlement endpoint only goes back 90 days).
2. Pulled `payments` (card only) and `refunds` from a restored copy of the
   28 Feb backup on hp-db-02, not prod.
3. Joined on `paybridge_payment_id` / `paybridge_refund_id`. Anything
   unmatched or with different amounts went into a spreadsheet and was
   checked by hand against `paybridge_events`, `audit_log` and the
   Paybridge dashboard.
4. For the tariff check, Finance's own spreadsheet recalculated expected
   prices for a random 2,000 bookings; we compared to `bookings.price_pence`.

Volumes: 18,412 settled card payments, 1,906 settled refunds, ~£436k gross.

## Findings

| # | What | Count | Money | Cause |
|---|---|---|---|---|
| 1 | Paid at Paybridge, no succeeded payment in Hallpass | 9 | £318.50 | Webhook processed once, failed, every retry dropped as duplicate (pre-Nov 2024 bug) |
| 2 | Refund settled at Paybridge, `submitted` in Hallpass | 11 | £402.00 | Webhook secret rotated 17 Jan without updating ours; fixed 21 Jan, after the 72h retry window |
| 3 | Refunds in Paybridge with no Hallpass record | 4 | £126.00 | Made by hand in the Paybridge dashboard by Finance staff |
| 4 | Duplicate auto-refund attempts | 2 | £0 | Resent `payment.succeeded` after hold expiry; Paybridge rejected the second refund |
| 5 | Payments with a different amount | 0 | — | — |
| 6 | Hallpass price ≠ Finance's tariff calculation | 612 of 2,000 sampled | 1–2p each | Concession rounding per slot (HP-412) |
| 7 | Hallpass price ≠ tariff, more than 2p | 7 | — | Bookings made 27–31 Mar 2024 for April dates, priced before the April rules were loaded |

### 1. Nine payments never recorded

All nine were October and early November 2024. Each had a
`paybridge_events` row with `processed_at` NULL and an error (lock timeout
against the hold expiry job — both touched the same booking). Paybridge
retried; we answered 200 "duplicate" to every retry. The holds then
expired, the bookings were cancelled, and the customers were charged for
nothing. Five of them had complained; the other four hadn't noticed.

All nine refunded in full on 12 March with an apology letter. This was
already fixed in Nov 2024 (`docs/findings/billing-webhook-duplicates-2024-11.md`);
no new cases after 6 November.

### 2. Eleven stuck refunds

The customers *had* their money back — Paybridge processed the refunds —
but Hallpass still showed them as in progress, so the payments were still
`succeeded` and the income report overstated income by £402. Fixed by
redelivering the events from the Paybridge dashboard (they were within the
dashboard's 90-day redelivery limit, just).

### 3. Dashboard refunds

Finance staff refunding directly in Paybridge, mostly for complaints that
came in by phone. Not wrong exactly, but invisible to Hallpass. Agreed with
Janet that discretionary refunds go through the back office from now on.

### 6. Penny differences

Not a reconciliation problem as such — Paybridge and Hallpass agree with
each other — but it's why Finance's spreadsheet never ties out exactly.
Written up in `docs/billing/concessions-and-rounding.md`.

## Conclusions

- No money lost by the council. £318.50 was owed to residents (now repaid).
- Webhook duplicate handling was the biggest real problem and is fixed.
- There was no routine check that would have caught any of this. We need one.

## Actions

- [x] Refund the nine residents (Finance, 12 Mar)
- [x] Redeliver the eleven refund events (Priya, 13 Mar)
- [x] Webhook secret setting accepts two secrets for rotation (Marcus, 3.1.0)
- [x] Nightly automated reconciliation with an email to Finance (Priya,
      shipped in 3.2.0). *Note Aug 2026: it has been checking the wrong day
      since it shipped, see HP-489.*
- [x] Store refund policy tier on refunds (3.2.0) — half the time on this
      audit went on working out which tier a refund came from.
- [ ] Fix concession rounding (HP-412) — parked, see known issues.
- [ ] Load new price rules at least a week before 1 April (added to the
      how-to; whether it happens is another matter).
