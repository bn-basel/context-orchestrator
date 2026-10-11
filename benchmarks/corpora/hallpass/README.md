# Hallpass

Hallpass is the facility booking system for the council's Leisure Services
department. Residents, clubs and community groups use it to hire sports halls,
meeting rooms, grass pitches and the music practice rooms at Northgate and
Eastfield; staff use the back office to run facilities, closures, invoices and
refunds.

> This repository is a synthetic fixture project; the council, people and services in it are fictional.

## Quick start (local dev)

You need Python 3.12 and a local PostgreSQL 16. Docker is fine for Postgres,
we don't containerise the app itself.

```bash
createdb hallpass_dev
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env            # then edit HALLPASS_DATABASE_URL
python -m hallpass.core.db migrate
flask --app hallpass.api.app run --debug
```

Seed data: `psql hallpass_dev -f db/seed/dev_seed.sql` gives you two facilities,
a handful of spaces and a test resident (`dev@example.invalid`). Magic links are
printed to the console in dev instead of emailed (see `HALLPASS_EMAIL_BACKEND`).

Run the tests with `pytest`. The DB tests need `HALLPASS_TEST_DATABASE_URL`
pointing at an empty database they are allowed to trash.

## Layout

| Path | What lives there |
|---|---|
| `src/hallpass/core/` | config, DB connection helpers, clock, errors, money + timezone helpers, feature flags |
| `src/hallpass/api/` | Flask blueprints. Thin on purpose, logic lives in the domain packages |
| `src/hallpass/bookings/` | availability, booking lifecycle, series, waitlist, blackouts |
| `src/hallpass/billing/` | pricing, concessions, invoices, Paybridge, refunds |
| `src/hallpass/accounts/` | residents, organisations, roles, magic-link login |
| `src/hallpass/notifications/` | outbox, templates, email + SMS (TextHub) |
| `src/hallpass/reports/` | usage and income reports for the service managers |
| `src/hallpass/worker.py` | cron entry point for background jobs |
| `db/migrations/` | plain SQL migrations, applied in filename order |
| `docs/` | architecture, conventions, ADRs, runbooks, meeting notes |

## Where to read next

- `docs/architecture.md` for the big picture
- `docs/conventions.md` before you open a PR
- `docs/constraints.md` for the things we are not allowed to change
- `docs/decisions/` for why things are the way they are
- `docs/runbooks/` if something is on fire

## Contacts

Product owner sits in Leisure Services (Customer & Bookings team). Infra (VMs,
Postgres, backups, the SMTP relay) is the council's Digital Infrastructure
team, raise a ticket in their queue, don't email individuals. Paybridge support
details are in the Paybridge outage runbook.
