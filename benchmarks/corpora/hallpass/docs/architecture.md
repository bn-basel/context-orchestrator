---
kind: doc
status: verified
---

# Hallpass architecture

Last properly reviewed: March 2025 (Priya). Some sections are older than that;
if something here disagrees with the code, the code wins and please fix this
page.

## One-paragraph version

A single Python 3.12 / Flask application talking to one PostgreSQL 16
database with hand-written SQL through psycopg 3. A cron-driven worker
process (same codebase, `hallpass.worker`) does everything that shouldn't
happen inside a web request: expiring holds, sending email/SMS from the
outbox, waitlist offers, invoices, reconciliation and data retention. Card
payments go to Paybridge's hosted checkout and come back to us as webhooks.
That's it. No queue broker, no cache server, no microservices. We have been
asked about all three and the answer so far has been "not worth it for ~400
bookings a day".

## Components

```
   residents / clubs          staff (back office)
          |                          |
          v                          v
   +----------------------------------------+
   |  council F5 load balancer (TLS ends)    |
   +----------------------------------------+
          |                          |
   hp-app-01 (gunicorn + cron)   hp-app-02 (gunicorn)
          \                          /
           \                        /
            +---- hp-db-01 (PG 16 primary) ---- streaming ---> hp-db-02 (replica)
                        |
                        +-- pgBackRest -> council object store (nightly full/diff + WAL)

   outbound: Paybridge API (HTTPS), TextHub API (HTTPS), council SMTP relay (port 25, internal)
   inbound:  Paybridge webhooks -> /api/payments/paybridge/webhook
```

Only hp-app-01 runs the worker crontab. If hp-app-01 is down for long, the
worker needs enabling on 02 by hand (see the deploy runbook). The advisory
locks in `worker.py` mean running it on both by accident is safe, just noisy.

## Packages

| Package | Owns |
|---|---|
| `hallpass.core` | settings, DB pool and helpers, clock, error types, pence and Europe/London helpers, feature flags |
| `hallpass.api` | Flask blueprints. Parse input, check who you are, call one domain function, serialise. |
| `hallpass.bookings` | availability search, holds/confirm/cancel, series, waitlist, blackouts, staff day sheet |
| `hallpass.billing` | price rules, concessions, Paybridge checkout + webhooks, refunds, invoices, reconciliation |
| `hallpass.accounts` | residents, organisations and membership, staff users, roles, magic-link login, retention |
| `hallpass.notifications` | outbox, templates, SMTP and TextHub senders, reminders |
| `hallpass.reports` | usage (utilisation) and income reports, CSV export |

Dependency direction: `api -> domain packages -> core`. Domain packages may
call each other (bookings calls billing for prices and refund quotes; billing
calls bookings to confirm a hold) but nothing imports `api`, and `core`
imports nothing from hallpass outside itself.

## Life of a booking

1. Resident searches availability for a space and date. Availability is
   computed on the 15-minute grid from opening hours, minus blackout periods,
   minus existing held/confirmed bookings.
2. They pick a slot; `POST /api/bookings` creates a row with
   `status = 'held'` and `hold_expires_at = now + 15 min`. The exclusion
   constraint `bookings_no_overlap` (ADR 0009) guarantees nobody else can hold
   or confirm an overlapping slot on that space in the meantime.
3. Price is worked out at hold time (`price_pence`), using price rules for
   the hirer type plus any concession.
4. Resident goes to Paybridge hosted checkout. We never see card details.
5. Paybridge calls our webhook. We store the raw event in `paybridge_events`
   (unique on event id), then billing marks the payment succeeded and asks
   bookings to confirm the hold. Confirmation email goes into
   `notifications_outbox` in the same transaction (ADR 0008).
6. If no payment arrives, the worker's `release_holds` job cancels the hold
   after it expires. Late webhooks for an expired hold get refunded
   automatically (this happens a few times a month).

Organisations that pay by invoice skip steps 4-5: their holds confirm
straight away and the booking lands on next month's invoice.

Cancellation → refund quote from billing (tiered by notice, ADR 0012) →
refund row → Paybridge refund API. Staff cancellations (e.g. because of a
closure) always refund in full.

## Time

Stored as `timestamptz` in UTC; the DB session is forced to UTC in
`core/db.py`. Everything a human sees or types is Europe/London. Conversion
only happens in `hallpass.core.tz`. Recurring series are generated in local
time and materialised as individual bookings (ADR 0005), which is where most of
our DST bugs have come from.

## Configuration and flags

Environment variables (`HALLPASS_*`, see `core/config.py`) for anything that
differs per environment or is secret. Behaviour switches that staff might want
to flip without a deploy are rows in `feature_flags` (ADR 0014).

## Things we don't have (yet)

- No read replica usage from the app. Reports run on the primary.
- No full-text search; the staff "find a hirer" box is an ILIKE.
- No API for third parties. A couple of clubs have asked.
- No staging Paybridge webhooks reaching laptops; use the sandbox replay
  script in `scripts/` instead.
