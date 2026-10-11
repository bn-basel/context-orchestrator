---
kind: known_issue
status: verified
---

# Known issues: billing (pricing, payments, refunds, invoices)

Newest at the top within each section. Ticket numbers are the Digital
service desk's HP- queue.

## Open

### HP-489 — Nightly reconciliation checks the wrong day

Found August 2026. The worker's `reconcile_paybridge` job runs at 03:30 and
passes **today's** date. At 03:30 there's almost nothing in today's
settlement file and almost nothing in our payments, so the job reports
nothing and **yesterday is never reconciled**. This has been the case since
3.2 (June 2025). The runbook's "only does today" line was describing the
bug, not a design. Manual runs (`python -m hallpass.billing.reconciliation
--day ...`) work fine.

Fix is one line in `worker.py` (`today_local() - 1 day`) plus back-filling
the missed days in batches so Finance don't get 400 emails at once. Waiting
on platform for the worker change.

### HP-412 — Concession rounding on odd amounts

Percentage concessions are applied per 30-minute slot with floor division,
not to the total with half-up rounding as ADR 0002 says. On odd half-hour
prices (e.g. 1375p from a £27.50/h rate) a 50% Leisure Card booking of 2
hours costs 2748p instead of 2750p. Knock-on effects: "You saved" + amount
paid ≠ full price on the checkout page; the income report overstates
concession value by the same pennies; Finance's recalculations are 1-2p off.

Always in the customer's favour; a few pounds a month in total. Fix is
known (discount the total, `split_evenly` across slots) but parked until the
tariff review in case rates move to whole pounds. Full write-up:
`docs/billing/concessions-and-rounding.md`. Strict xfail tests mark it.

### HP-466 — Charity VAT exemption is an unconfirmed assumption

Invoices to organisations with a charity number show no VAT. Nobody in
Finance has confirmed that's right, and we suspect it isn't. See
`docs/billing/assumptions-vat.md` for what to do if it turns out wrong.
Blocked on Finance since January 2024.

### HP-430 — Duplicate Paybridge webhook deliveries (mitigated, not closed)

Paybridge delivers webhooks at least once; doubles of the same event arrive
a few times a week and dashboard "Resend" creates new event ids. Since the
Nov 2024 fix (see `docs/findings/billing-webhook-duplicates-2024-11.md`)
duplicates are harmless as far as we know. Left open because:

- When `payment.succeeded` overtakes our own payments INSERT, the event
  fails with `UnknownPayment` and waits for the 5-minute backlog job. The
  customer stares at "checking your payment" for up to 5 minutes.
- About 30 events from 2024-25 sit permanently unprocessed (genuinely
  unknown payments, mostly from the test-mode link that went live by
  mistake in May 2024). The backlog stops retrying after 72h but they show
  in every "unprocessed events" query. Someone should mark them by hand.
- Before 3.1.0, a resent `payment.succeeded` for an already-refunded
  payment failed with `UnknownPayment`. Fixed, but the old ones are in the
  30 above.

### HP-447 — "7 days' notice" is 168 hours, not a calendar week

Refund tiers measure elapsed time. A resident who cancels at 10:00 on
Saturday 28 March 2026 for a booking at 10:00 on Saturday 4 April gets 50%,
not 100%, because the clocks went forward in between and it's only 167
hours. The cancel page shows the right (50%) figure before they confirm, so
it's a "that's not what the leaflet says" complaint rather than a wrong
refund. Three or four a year, all in spring. Leisure ops say just refund
the difference manually. Fixing it properly means deciding whether notice is
local-calendar based, which ADR 0012 doesn't say.

### HP-377 — Block-booking discount counts sessions per month

On invoices, the 10% block discount needs 10 sessions of a series in the
same month. A 12-week series split 6 + 6 across two months gets no discount
at all. One club has complained (Riverside Juniors, March 2025); Finance
credited them by hand. Fix: count the series, not the month. Also note the
VAT series rule uses the *whole* series, so the two disagree.

### Residents never get the block-booking discount

`quote_price` supports it, but bookings doesn't pass the series length, so
resident series are always full price. No ticket. Nobody has noticed, or
everyone has and assumed it's policy.

### Settlement day boundary (won't fix)

Paybridge settlement days are UTC; our reconciliation days are local. In
BST, payments between 00:00 and 01:00 local show up as `missing_remotely`
one night and `missing_locally` the next. Finance know to look at the next
day's email.

### Small ones

- `refunds.refund_preview` always uses v2 and ignores the
  `refund_policy_v2` flag. If anyone ever turns the flag off, the cancel
  page and the actual refund will disagree.
- `PaybridgeClient.settlements` doesn't follow pagination (limit 500/day).
  Our busiest day so far was ~310 settlements (September 2025 club
  registrations). Will bite eventually.
- Refund retry after 24h is not protected by Paybridge idempotency. Check
  the dashboard before retrying an old failed refund.
- Two checkouts for one booking in two browser tabs can both succeed. We
  then have two succeeded payments for one booking. Happens ~once a quarter,
  always via a complaint. Refund one manually.
- The out-of-borough uplift is added to the first slot only. Invisible to
  customers, but confusing if you look at quote lines when debugging.

## Fixed

- **HP-430 (main part)**, Nov 2024 — failed webhook processing + duplicate
  dedupe meant some payments were never recorded. Upsert with
  `processed_at` check, savepoint around handlers, backlog retries.
- **Jan 2025** — webhook secret rotated in Paybridge but not in our config.
  All webhooks 403'd for ~4 days, beyond Paybridge's 72h retry window; 11
  refunds stuck as `submitted`. Found by the March 2025 audit. Secret
  setting now accepts two values for rotation; runbook updated.
- **Double auto-refunds** (2024) — duplicate `payment.succeeded` for a
  payment that arrived after its hold expired created two
  `hold_expired_before_payment` refunds. Paybridge rejected the second.
  `create_refund_row` now caps at the refundable remainder.
- **HP-301**, 2.2.1 — "Pay again" returned the customer's old expired
  Paybridge session because the checkout reference (and so the idempotency
  key) was reused. Reference now includes an attempt number.
