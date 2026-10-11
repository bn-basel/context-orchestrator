# Changelog

Format loosely follows Keep a Changelog. Dates are release dates to
production. Older entries were reconstructed from git tags in 2024 and are
patchier.

## Unreleased

- Usage report: separate column for maintenance windows vs closures
  (uses `blackout_periods.kind`).
- Remove `legacy_healthz` once infra confirm the F5 probe uses `/health/ready`.

## 3.4.2 - 2026-09-15

### Fixed
- Worker `schedule_reminders` computed "tomorrow" in UTC around midnight, so
  bookings at 00:30-01:00 BST got reminders a day late. Now uses
  `clock.today_local()`.
- CSV export: pence columns were formatted as `£1,234.00` for large values
  and plain numbers for small ones. Excel hated it. Still not ideal.

## 3.4.1 - 2026-08-18

### Fixed
- Feature flag cache never refreshed if the first load failed (cold process
  during a DB restart). Now retries on next check.

## 3.4.0 - 2026-03-10

### Added
- Staff can set a blackout `kind` (closure / maintenance / event / weather).
- `peak_hours` report for service managers.

### Changed
- Income report includes invoice-paid org bookings (previously card only,
  which finance had been adding by hand. Sorry, Janet).

## 3.3.0 - 2025-09-30

### Added
- CSV download for usage and income reports.
- `outstanding_invoices` report.

### Changed
- Accessibility fixes from the Sept 2025 external audit (focus order on the
  slot picker, error summary on forms, colour contrast on the calendar).

## 3.2.1 - 2025-07-22

### Fixed
- Clearer error when Paybridge rejects our API key (was a generic 500).
  Prompted by the key expiring on 21 July.

## 3.2.0 - 2025-06-03

### Added
- Worker jobs renamed (`release_holds`, `schedule_reminders`,
  `retention_sweep`, ...). **Update the crontab on hp-app-01 with this release.**
- `submit_refunds` worker job: Paybridge refund calls no longer happen inside
  the cancel request, so a Paybridge timeout can't roll back a cancellation.
- Sign out everywhere (`session_epoch`), staff magic-link login, soft-removed
  org members, waitlist status rework, nightly Paybridge reconciliation.
  Migration 0010.
- Percentage rollout for feature flags is now actually used by the waitlist
  (Northgate at 50%).

## 3.1.0 - 2025-04-08

### Changed
- Magic links valid for 20 minutes instead of 60.
- Structured JSON logging in production (`HALLPASS_LOG_JSON`).

## 3.0.0 - 2025-01-14

### Changed
- **Python 3.12** and the new RHEL 9 app VMs (hp-app-01/02). Python 3.11 is
  no longer supported.
- psycopg 3.2 with `psycopg_pool`; connection setup forces `TIME ZONE 'UTC'`.
- Dropped the `HALLPASS_DB_DSN` alias, use `HALLPASS_DATABASE_URL`.

## 2.6.0 - 2024-11-05

### Removed
- Staff SQL console. Yes, really. Use reports or ask a developer.

### Added
- `audit_log` rows for every refund and price rule change.

## 2.5.0 - 2024-06-11

### Changed
- Holds last 15 minutes (was 10). Configurable with `HALLPASS_HOLD_MINUTES`.
- Payment arriving after a hold expired: confirm if the slot is still free,
  otherwise refund automatically.

## 2.4.0 - 2024-04-16

### Added
- `no_show` booking status and a button on the staff day sheet
  (flag `no_show_tracking`). Migration 0009.
- Feature flags: `rollout_percent` and per-facility `facility_ids`.

## 2.3.0 - 2024-03-26

### Changed
- **Slots are now 30 minutes** (ADR 0011, migration 0008). Existing
  quarter-hour bookings left alone.
- Income report recognises income on the booking date (see Jan 2024 reporting
  meeting notes).

## 2.2.0 - 2024-03-05

### Added
- Feature flags table (ADR 0014, migration 0007).
- Waitlist, piloted at Eastfield behind `waitlist`.

## 2.1.0 - 2024-02-06

- Refund policy v2: tiered by notice period (ADR 0012).
- Monthly invoices for organisations (`org_invoicing`).

## 2.0.0 - 2024-01-09

- Organisations and organisation members; org admins can book on behalf of a
  club.
- Recurring/block bookings materialised as individual rows (ADR 0005).
- Exclusion constraint for double booking was already in place since 1.0, but
  2.0 removed the old application-level lock table it was meant to replace.

## 1.2.0 - 2023-11-28

- Consents and audit log (migration 0006) following the DPIA.
- SMS via TextHub (reminders, off by default... we think).

## 1.1.0 - 2023-10-24

- Northgate Community Centre and the music practice rooms onboarded.
- Blackout periods (closures) managed by staff.

## 1.0.0 - 2023-09-18

- First production release. Eastfield Leisure Centre only. Residents book
  sports halls and meeting rooms on a 15-minute grid, pay by card via
  Paybridge, sign in with emailed magic links.
