# Hallpass corpus spec (authoring brief, not part of the corpus)

This brief is given to the authors of the synthetic "Hallpass" project in
`benchmarks/corpora/hallpass/`. It lives outside that folder on purpose: it
must never be ingested, because it would summarise everything in one place.

## The project

Hallpass is the booking system of a mid-sized UK city council's Leisure
Services department. Residents, clubs and charities book community facilities
(sports halls, meeting rooms, grass pitches, music practice rooms) by the
hour; staff manage facilities, closures and money. It has been in production
for about three years, built by a small in-house team (4 developers have come
and gone), so the docs vary in quality, tone and age.

- Python 3.12 service, package `hallpass` under `src/hallpass/`.
- PostgreSQL 16 accessed with psycopg 3 and hand-written SQL. **No ORM.**
- HTTP handlers in `src/hallpass/api/`; background jobs run by a cron-driven
  worker (`src/hallpass/worker.py`).
- Money is integer **pence** (GBP). Timestamps are stored in UTC; bookable
  slots are defined in **Europe/London local time** (so DST matters).
- Card payments go through a (fictional) provider called **Paybridge**
  (hosted checkout + webhooks). Invoices for organisations are paid by bank
  transfer.
- Email via the council's SMTP relay, SMS via a (fictional) gateway **TextHub**.

## Domain vocabulary (use it naturally and inconsistently, like real teams)

booking / reservation / hire; resident / customer / hirer / account holder;
organisation / club / group; facility (a building) / space (a bookable room or
pitch inside it); slot / session; cancel / withdraw; refund / credit;
concession / discount; blackout / closure / maintenance window; series /
recurring booking / block booking.

## Database tables (owned by area D's migrations; everyone references these names)

residents, organisations, organisation_members, staff_users, facilities,
spaces, opening_hours, blackout_periods, bookings, booking_series,
waitlist_entries, price_rules, concessions, invoices, invoice_lines, payments,
refunds, paybridge_events, notifications_outbox, consents, audit_log.

Key columns everyone may rely on: `bookings(id, space_id, resident_id,
organisation_id, series_id, starts_at, ends_at, status, price_pence,
created_at, cancelled_at)`; booking `status` ∈ {held, confirmed, cancelled,
no_show}; `payments(id, booking_id, invoice_id, amount_pence,
paybridge_payment_id, status, created_at)`; `refunds(id, payment_id,
amount_pence, reason, status, created_at)`.

## Architecture decision records (docs/decisions/NNNN-title.md)

Numbers and statuses are fixed so cross-references stay consistent. The owner
area writes the file; others may cite it by number.

| ADR | Title | Status | Area |
|---|---|---|---|
| 0001 | PostgreSQL with psycopg and plain SQL, no ORM | verified | D |
| 0002 | Money as integer pence | verified | B |
| 0003 | 15-minute slot granularity | superseded by 0011 | A |
| 0004 | Passwordless login with emailed magic links | verified | C |
| 0005 | Materialise recurring bookings as individual rows | verified | A |
| 0006 | Paybridge as card payment provider | verified | B |
| 0007 | Refund policy v1: full refund up to 24h before start | superseded by 0012 | B |
| 0008 | Transactional outbox for notifications | verified | C |
| 0009 | Prevent double booking with a Postgres exclusion constraint | verified | A |
| 0010 | Personal data retention: 6 years for financial, 2 years otherwise | verified | C |
| 0011 | 30-minute slot granularity | verified | A |
| 0012 | Refund policy v2: tiered by notice period | verified | B |
| 0013 | Store slot boundaries as local wall-clock time plus zone | unverified (proposed) | A |
| 0014 | Feature flags in a database table | verified | D |

## Front matter conventions (the tool that reads these docs understands them)

Markdown files may start with:

```
---
kind: decision | convention | constraint | known_issue | finding | doc
status: verified | unverified | assumption | superseded
---
```

Use it on most docs, but not all (real teams forget). ADRs: `kind: decision`
and the status from the table. Known issues: `kind: known_issue`. Findings
(investigations, audits, load tests with conclusions): `kind: finding`,
usually `verified`. Things the team believes but has not confirmed:
`status: assumption`.

## Areas and authors

Each author writes **only** inside their own paths. Target ~15–18k tokens
(roughly 60–70 KB of text) per area, spread over many realistic files.

**A. Bookings and scheduling.** `src/hallpass/bookings/` (availability,
booking lifecycle, recurring series, waitlist, blackouts), `tests/bookings/`,
ADRs 0003, 0005, 0009, 0011, 0013, `docs/bookings/` (how-to and design notes),
`docs/known-issues/bookings.md`, at least one `docs/findings/` file (e.g. a
load test of the availability search). Must include: a known DST bug in
recurring series; a waitlist promotion race condition; an open question about
what happens to a series when a blackout overlaps it.

**B. Pricing, payments and refunds.** `src/hallpass/billing/` (pricing,
concessions, invoices, payments, Paybridge webhooks, refunds),
`tests/billing/`, ADRs 0002, 0006, 0007, 0012, `docs/billing/`,
`docs/known-issues/billing.md`, findings (e.g. a reconciliation audit
between Paybridge and the ledger). Must include: a rounding issue when
percentage concessions apply to odd amounts; duplicate Paybridge webhook
deliveries; an *assumption* that registered charities are VAT-exempt for
hires (not confirmed with finance).

**C. Accounts, access and notifications.** `src/hallpass/accounts/`
(residents, organisations, roles, magic-link auth),
`src/hallpass/notifications/` (outbox, templates, email, SMS),
`tests/accounts/`, `tests/notifications/`, ADRs 0004, 0008, 0010,
`docs/accounts/`, `docs/notifications/`, `docs/privacy.md` (constraints),
`docs/known-issues/accounts-and-notifications.md`. Must include: SMS sent
twice when the worker retries; an *assumption* that SMS reminders are opt-in
by default; the role model (resident, org admin, facility staff, finance,
superuser).

**D. Platform, operations and cross-cutting docs.** `README.md`,
`docs/architecture.md`, `docs/conventions.md`, `docs/constraints.md`,
ADRs 0001 and 0014, `db/migrations/0001_*.sql` … (all tables above, spread
over 6–10 migrations in a believable order, including one that alters an
earlier table), `pyproject.toml`, `src/hallpass/core/` (config, db, clock,
errors, money helpers, timezone helpers, feature flags), `src/hallpass/api/`
(thin HTTP handlers for the other areas), `src/hallpass/worker.py`,
`src/hallpass/reports/` (usage and income reports), `docs/runbooks/` (deploy,
restore from backup, Paybridge outage), `CHANGELOG.md`, `docs/meetings/` (2–3
meeting notes where decisions were discussed but never written up as ADRs).

## Writing guidance for all authors

- Make it feel like a real, slightly messy codebase: varied tone and depth,
  a few TODOs, occasional outdated statements, docs that partly repeat each
  other in different words. Do not write a single document that summarises
  everything.
- Python must be syntactically valid 3.12 (it is parsed, never run). Tests
  should look like real pytest tests.
- Do not mention benchmarks, retrieval, evaluation, labels or that the project
  is synthetic anywhere except one line in `README.md` (area D).
- Use the table names, ADR numbers and module paths above; invent anything
  else you need inside your own area.
