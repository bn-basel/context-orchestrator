# Hallpass corpus notes (not part of the corpus)

Four separate authors wrote areas A–D in parallel from `hallpass.spec.md`
(2026-10-11); the root `src/hallpass/__init__.py` and `tests/conftest.py`
were added afterwards. Size at commit: 164 files, ~566 KB, ~141k tokens
(estimated), 1,030 chunks.

The authors reconciled most cross-area names, but some drift remains. It is
left in on purpose (real codebases drift) and is listed here so nobody
mistakes it for a corpus error:

- `bookings/notify.py` was removed by its author; any remaining references
  to `enqueue(kind=, channel=, recipient=, payload=)` predate C's final
  outbox API (`enqueue(conn, *, template=, booking_id=…)`).
- Columns used by code but absent from migrations: `bookings.reminder_queued_at`,
  `waitlist_entries(resident_id, space_id, starts_at, ends_at)`,
  `facilities.name`, `spaces.name`; table `resident_concessions`.
- `tests/bookings/conftest.py` inserts `organisations.pays_by_invoice`; the
  column is `on_account`.
- Column naming differs between areas in places (e.g. residents
  `display_name`/`mobile` vs `full_name`/`phone`).
- Person names overlap inconsistently across areas (e.g. "Priya Nair" /
  "Priya Raman", two different "Janet"s).
- Deliberately outdated statements: `docs/bookings/phone-bookings.md` (10-minute
  holds), `docs/billing/README.md` (refunds sent during the cancel request),
  hotfix 2.6.1 missing from the changelog.
- Known bug left in code on purpose: `worker.reconcile_paybridge` passes
  today's date (HP-489).
