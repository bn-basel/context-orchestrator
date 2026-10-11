---
kind: convention
status: verified
---

# Conventions

House rules for code in this repo. Most of these exist because we got burnt
once. If you want to change one, raise it at the fortnightly tech catch-up
rather than just doing it in a PR.

## Python

- Python 3.12, ruff for lint + import order, line length 100.
- Type hints on public functions in `core` and `billing` (mypy runs on those).
  Elsewhere they're encouraged but CI won't fail you.
- No `datetime.now()` / `datetime.utcnow()` / `date.today()`. Use
  `hallpass.core.clock`. Ruff's DTZ rules are on to catch naive datetimes.
- Logging via `logging.getLogger(__name__)`. **Never log personal data**:
  no emails, phone numbers, names, postcodes. Log ids. (We had to scrub a
  month of logs in 2024 because of a debug line in the magic-link code.)

## SQL and the database

- Plain SQL strings with named parameters (`%(name)s`). No ORM, no query
  builder (ADR 0001). f-strings in SQL are only OK for identifiers that come
  from a fixed whitelist in the same function, and you must comment why.
- Use the helpers in `core/db.py` (`fetch_one`, `fetch_all`, `execute`,
  `transaction`). Don't open your own connections in request code.
- Keep long queries as module-level constants (`_SOMETHING_SQL`) so they show
  up in grep and diffs.
- Tables are plural snake_case; foreign keys are `<singular>_id`; timestamps
  end in `_at` and are `timestamptz`; local dates are `date`; booleans read as
  a statement (`is_in_borough`, `active`, `bookable`).
- Status columns are `text` with a CHECK constraint, not Postgres enums
  (altering enums inside a transaction was painful on PG 12 and we never went
  back).
- Migrations: `db/migrations/NNNN_short_name.sql`, forward-only, one
  `BEGIN; ... COMMIT;` per file. Never edit a migration that has run in
  production; write a new one. Anything that rewrites a big table (bookings,
  audit_log, notifications_outbox) needs to be run past the infra DBA first.

## Money

- Integer pence, always, everywhere: DB, Python, JSON (ADR 0002). Field names
  end in `_pence`.
- Rounding: half-up to the penny via `core.money` helpers. Don't use
  `round()` on floats for money. Don't use floats for money at all.
- Format for humans only at the edge (`money.format_gbp`) - templates and CSV.

## Time

- UTC in storage, Europe/London for anything human. Convert only through
  `core.tz`.
- API timestamps are ISO 8601 *with* offset. Naive strings get a 400.
- Slots are on the 30-minute grid (ADR 0011). The DB check constraint enforces
  it for new rows.

## HTTP handlers ("thin handlers")

A handler in `hallpass.api` should: parse/validate input, establish the
principal and role, open a transaction, call **one** domain function,
return JSON. Business rules in handlers get bounced in review. If two
handlers need the same logic, it goes in the domain package, not a shared
helper in `api`.

Errors: raise from `core.errors` (`ValidationError`, `PolicyError`,
`ConflictError`, ...). The app factory maps them to status codes. Error bodies
look like `{"error": "slot_taken", "message": "..."}`.

## Background work

Anything slow, retryable, or talking to a third party (except the Paybridge
checkout redirect, which the user waits on) happens in the worker. Jobs must be
idempotent - cron will happily run them again after a failure.

Outbound email/SMS: insert into `notifications_outbox` in the same transaction
as the change that caused it (ADR 0008). Never call SMTP/TextHub from a request.

## Feature flags

New user-visible behaviour goes behind a flag in `feature_flags` (ADR 0014)
unless it's a bug fix. Add the row in a migration with `enabled = false`.
Remove the flag and the dead branch once it has been on everywhere for a
month. (We are bad at this last part; `paybridge_checkout_v2` has been fully
on since forever.)

## Tests

- pytest. DB tests are marked `@pytest.mark.db` and run against a throwaway
  database; each test runs in a transaction that's rolled back.
- Freeze time with `clock.frozen(...)` or freezegun. Any test that touches
  dates should have a DST-day variant if it plausibly could break.
- External services are faked (`respx` for HTTP). Nothing in the test suite
  may hit Paybridge sandbox or TextHub.

## Git / PRs

- Branch from `main`, short-lived. Squash merge.
- PR title is what goes in the changelog, so make it readable.
- One approving review. Two if it touches billing, migrations or auth.
- Update `CHANGELOG.md` under "Unreleased" in the same PR.
