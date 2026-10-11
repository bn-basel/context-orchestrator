# Retrieval evaluation: hallpass

- Run: `20261011T013402Z-hallpass`, commit `2d07cd5a85`
- Config: max_tokens=4000, per_kind_limit=6
- Corpus: 163 files, 1035 chunks, ~139612 tokens (estimated)

| Task | Category | Recall | Precision | First hit | Items | ~Tokens | Missed |
|---|---|---|---|---|---|---|---|
| H01 | bugfix | 0.60 | 0.18 | 2 | 17 | 4605 | src/hallpass/bookings/recurring.py:69-95, src/hallpass/core/tz.py:42-50 |
| H02 | bugfix | 0.67 | 0.36 | 1 | 11 | 4469 | src/hallpass/bookings/waitlist.py:105-124, src/hallpass/core/db.py:126-138 |
| H03 | bugfix | 0.60 | 0.20 | 1 | 15 | 4514 | src/hallpass/bookings/recurring.py:235-261, src/hallpass/bookings/lifecycle.py:178-191 |
| H04 | bugfix | 0.60 | 0.18 | 1 | 17 | 4248 | src/hallpass/bookings/blackouts.py:180-192, src/hallpass/bookings/availability.py:60-77 |
| H05 | bugfix | 0.60 | 0.19 | 1 | 16 | 4499 | src/hallpass/billing/refunds.py:163-170, src/hallpass/api/bookings.py:77-85 |
| H06 | feature_constrained_by_decision | 0.50 | 0.18 | 5 | 17 | 4621 | docs/notifications/adding-a-notification.md:5-33, docs/decisions/0008-transactional-outbox-for-notifications.md:24-38, src/hallpass/notifications/templates.py:20-32 |
| H07 | feature_constrained_by_decision | 0.17 | 0.05 | 1 | 19 | 4645 | docs/decisions/0014-feature-flags-in-database.md:27-43, docs/conventions.md:80-86, db/migrations/0007_feature_flags.sql:7-19, src/hallpass/core/flags.py:64-94, src/hallpass/api/staff.py:140-146 |
| H08 | feature_constrained_by_decision | 0.83 | 0.29 | 1 | 17 | 4476 | src/hallpass/bookings/lifecycle.py:50-54 |
| H09 | feature_constrained_by_decision | 0.83 | 0.28 | 2 | 18 | 4164 | docs/accounts/roles.md:49-49 |
| H10 | schema_or_migration | 1.00 | 0.20 | 1 | 25 | 4893 | - |
| H11 | schema_or_migration | 0.50 | 0.25 | 1 | 12 | 4418 | src/hallpass/bookings/availability.py:119-125, src/hallpass/reports/usage.py:42-47, docs/conventions.md:38-41 |
| H12 | cross_area | 1.00 | 0.31 | 2 | 16 | 4543 | - |
| H13 | cross_area | 0.67 | 0.22 | 1 | 18 | 4614 | src/hallpass/billing/refunds.py:111-138, docs/notifications/adding-a-notification.md:5-33 |
| H14 | cross_area | 0.60 | 0.20 | 1 | 15 | 4523 | src/hallpass/bookings/lifecycle.py:205-213, src/hallpass/notifications/recipients.py:66-108 |
| H15 | superseded_trap | 0.40 | 0.13 | 2 | 15 | 4422 | src/hallpass/notifications/templates/booking_cancelled.email.txt:1-7, docs/notifications/adding-a-notification.md:9-13, src/hallpass/notifications/recipients.py:50-63 |
| H16 | superseded_trap | 0.60 | 0.14 | 1 | 21 | 4698 | src/hallpass/bookings/slots.py:23-34, docs/bookings/availability-search.md:62-66 |
| H17 | assumption_trap | 1.00 | 0.29 | 1 | 17 | 4593 | - |
| H18 | assumption_trap | 1.00 | 0.24 | 1 | 21 | 4410 | - |
| H19 | missing_information | 0.40 | 0.11 | 1 | 18 | 3926 | db/migrations/0009_no_show_and_flag_rollout.sql:9-17, src/hallpass/reports/usage.py:1-9, docs/notifications/reminders.md:8-10 |
| H20 | missing_information | 0.40 | 0.17 | 1 | 12 | 4442 | docs/bookings/blackouts-and-series.md:13-30, docs/bookings/blackouts-and-series.md:49-66, src/hallpass/bookings/blackouts.py:164-167 |

Mean recall 0.65, mean precision 0.21, mean package ~4486 tokens = 0.03 of the full corpus.
Forbidden items returned: 0. Expected-unresolved misses: 2. Status mismatches: 0.

Recall by category: assumption_trap 1.00, bugfix 0.61, cross_area 0.76, feature_constrained_by_decision 0.58, missing_information 0.40, schema_or_migration 0.75, superseded_trap 0.50
