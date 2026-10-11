---
kind: doc
status: verified
---

# Billing

Everything to do with money: what a hire costs, who gets a discount, taking
card payments through Paybridge, invoicing organisations, and refunds.

Code: `src/hallpass/billing/`. Tests: `tests/billing/`. Money is always
integer pence (ADR 0002) — if you see a float near money, it's a bug.

## The short version

1. A resident picks a slot. `bookings` asks `billing.pricing.quote_price`
   what it costs. The answer (VAT-inclusive, after any concession) goes into
   `bookings.price_pence` and is never recalculated.
2. Resident bookings are **held** and paid by card on Paybridge's hosted page.
   The booking only becomes confirmed when Paybridge's `payment.succeeded`
   webhook arrives. Never from the browser redirect.
3. Organisations with `pays_by_invoice` skip payment. On the 1st of the
   month they get one invoice for last month's bookings, payable by bank
   transfer within 30 days.
4. Cancellations: refund depends on notice (ADR 0012). The refund is sent to
   Paybridge straight away as part of the cancel request.
5. Each night we compare Paybridge's settlement report with our payments.

## Modules

| Module | What it does |
|---|---|
| `pricing.py` | `price_rules` → price per 30-min slot, local time. `quote_price` is the entry point. |
| `concessions.py` | Leisure Card / U18 / Over 65 etc. and the 10% block-booking discount |
| `vat.py` | Standard vs exempt, gross → net + VAT for invoice PDFs |
| `invoices.py` | Monthly organisation invoices, bank transfer matching |
| `paybridge.py` | HTTP client (httpx) |
| `payments.py` | Starting a checkout, recording success/failure |
| `webhooks.py` | Signature check, dedupe, dispatch, backlog retry |
| `refunds.py` | Policy (pure function `decide`), refund rows, sending to Paybridge |
| `reconciliation.py` | Nightly settlement vs ledger comparison |

## Worker jobs that belong to billing

- `process_paybridge_backlog` — every 5 min; retries stored webhook events
  that failed or were never processed.
- `submit_refunds` — every 5 min; sends requested refunds to Paybridge.
- `generate_invoices` — 1st of the month, behind `org_invoicing`.
- `reconcile_paybridge` — nightly.

## Other docs in this folder

- `how-to-price-rules.md` — adding or changing a tariff
- `how-to-manual-refund.md` — discretionary refunds, and fixing stuck ones
- `paybridge-webhooks.md` — design notes on the webhook handler
- `concessions-and-rounding.md` — why the pennies don't add up
- `invoicing.md` — organisation invoices
- `finance-guide.md` — for Finance, no code
- `assumptions-vat.md` — what we believe about VAT and haven't confirmed

Known problems: `docs/known-issues/billing.md`.

## Gotchas

- `bookings.price_pence` is a snapshot. Changing a price rule never changes
  existing bookings. That's on purpose — people agreed to a price.
- Peak / off-peak doesn't exist as a concept in the schema. It's just two
  rules with different rates and times.
- Test keys for Paybridge start `pb_test_`. The sandbox is at
  `sandbox.paybridge.example`. Webhooks in dev: use the Paybridge CLI's
  `listen --forward-to localhost:8000/api/payments/paybridge/webhook`.
