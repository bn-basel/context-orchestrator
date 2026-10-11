---
kind: decision
status: verified
---

# ADR 0014: Feature flags in a database table

Date: 2024-02-27
Author: Priya Nair
Reviewed: Tom Ellery, Leisure Services product owner

## Context

Until now, switching behaviour on and off meant an environment variable and a
deploy. That has hurt us three times:

1. The waitlist had to be turned on for Eastfield only (pilot) and off at
   Northgate, and env vars are global.
2. SMS reminders had to be switched off in a hurry when TextHub was double-
   sending; that took a change request and an out-of-hours deploy.
3. Leisure Services want to launch things on a date of their choosing
   (usually the start of a school term), not on our deploy day.

Third-party flag services (LaunchDarkly etc.) are out: paid SaaS, procurement,
and another data processor.

## Decision

- A `feature_flags` table: `key`, `enabled`, `description`, `updated_by`,
  `updated_at` (migration 0007). Later extended with `rollout_percent` and
  `facility_ids` (migration 0009).
- Read through `hallpass.core.flags.is_enabled(key, facility_id=, subject=)`.
  Unknown keys are off.
- Cached per process for 60 seconds. Accept that a flip takes up to a minute
  to reach all web workers.
- Superusers flip flags in the back office; each flip writes an `audit_log`
  row.
- Flags are added by migration (default off) and removed by migration once
  the feature is permanent.

Environment variables remain for secrets and per-environment settings. A flag
is not a config store; don't put URLs or numbers in it (rollout percent
excepted).

## Consequences

- Product can schedule launches with us flipping a switch at 9am, no deploy.
- Per-facility pilots are easy.
- Flags can now be changed in prod by people who aren't developers. The audit
  row is the mitigation.
- Every flag check is a potential stale-branch. We need the discipline to
  remove them; see conventions.
- If the DB is unreachable, `is_enabled` keeps the last cached values (or
  returns False on a cold process). That's acceptable because nothing works
  without the DB anyway.
