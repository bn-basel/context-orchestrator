---
kind: decision
status: verified
---

# ADR 0002: Money as integer pence

- Date: 2023-06-08
- Deciders: Tom Ellery, Aisha Okafor
- Related: ADR 0001, ADR 0006

## Context

Hallpass takes card payments, issues refunds and sends invoices. All amounts
are in GBP. The old Access database stored prices as `Currency` and the
Excel tariff sheet Finance gives us uses formulas with floating point
percentages, and between them they produced the classic "£0.1 + £0.2" bugs
that Finance spent time reconciling by hand.

Paybridge's API takes and returns amounts as integers in the minor unit
(pence). Postgres has `numeric`, which would be exact, but psycopg turns it
into `Decimal`, which then has to be converted at every JSON boundary and
every Paybridge call.

## Decision

- Every amount is an `int` number of **pence**, everywhere: database columns
  (`integer`, named `*_pence`), Python, JSON responses, logs.
- Never `float`. Never `numeric` columns.
- Conversion to `£12.34` happens only for display (`hallpass.core.money.format_gbp`).
- When a percentage has to be applied (concessions, VAT, partial refunds),
  compute it exactly and round **half up to the nearest penny, once, at the
  end**. Helpers in `hallpass.core.money` (`percent_of`, `vat_from_gross`).
- `integer` (32-bit) is fine: the largest single amount we expect is an annual
  invoice for a school, comfortably under £21m.

## Consequences

- Paybridge amounts can be stored and compared directly, no conversion.
- Rounding is a decision you have to make each time you multiply by a
  percentage. "Once, at the end" sounds obvious; see below.
- The tariff sheet has hourly rates. We charge per 30-minute slot, so odd
  hourly rates don't halve exactly. Pricing rounds the half-hour up. (That
  was decided later, when ADR 0011 changed the slot length, and nobody
  updated this ADR at the time.)

### Note added April 2025

The concession code (`billing/concessions.py`) does *not* follow the "once,
at the end" rule: it applies the percentage to each half-hour line and
floors each one. That predates the `core.money` helpers. It produces 1-2p
differences against everything else that uses `percent_of` on totals.
Tracked as HP-412, see `docs/known-issues/billing.md`. The decision above
still stands; the code is what's wrong.
