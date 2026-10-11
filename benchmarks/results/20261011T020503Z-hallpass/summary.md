# Retrieval evaluation: hallpass

- Run: `20261011T020503Z-hallpass`, commit `8e99dddafe`
- Config: max_tokens=4000, per_kind_limit=3, min_relative_score=0.0, max_references=4
- Corpus: 163 files, 1035 chunks, ~139612 tokens (estimated)

| Task | Category | Recall | Precision | First hit | Items | ~Tokens | Missed |
|---|---|---|---|---|---|---|---|
| H01 | bugfix | 0.40 | 0.20 | 2 | 10 | 3954 | src/hallpass/bookings/recurring.py:69-95, src/hallpass/core/tz.py:42-50, docs/bookings/time-and-dst.md:8-17 |
| H02 | bugfix | 0.83 | 0.71 | 1 | 7 | 3936 | src/hallpass/core/db.py:126-138 |
| H03 | bugfix | 0.60 | 0.33 | 1 | 9 | 3958 | src/hallpass/bookings/recurring.py:315-364, src/hallpass/bookings/recurring.py:235-261 |
| H04 | bugfix | 0.60 | 0.33 | 1 | 9 | 2791 | src/hallpass/bookings/blackouts.py:180-192, src/hallpass/bookings/availability.py:60-77 |
| H05 | bugfix | 0.60 | 0.27 | 1 | 11 | 3948 | src/hallpass/billing/refunds.py:163-170, src/hallpass/api/bookings.py:77-85 |
| H06 | feature_constrained_by_decision | 0.33 | 0.14 | 6 | 14 | 3980 | docs/notifications/adding-a-notification.md:5-33, docs/decisions/0008-transactional-outbox-for-notifications.md:24-38, src/hallpass/notifications/recipients.py:26-38, src/hallpass/notifications/templates.py:20-32 |
| H07 | feature_constrained_by_decision | 0.17 | 0.06 | 1 | 16 | 3898 | docs/decisions/0014-feature-flags-in-database.md:27-43, docs/conventions.md:80-86, db/migrations/0007_feature_flags.sql:7-19, src/hallpass/core/flags.py:64-94, src/hallpass/api/staff.py:140-146 |
| H08 | feature_constrained_by_decision | 0.67 | 0.36 | 1 | 11 | 2767 | src/hallpass/bookings/lifecycle.py:50-54, src/hallpass/core/config.py:104-104 |
| H09 | feature_constrained_by_decision | 0.67 | 0.44 | 2 | 9 | 1767 | docs/constraints.md:28-30, docs/accounts/roles.md:49-49 |
| H10 | schema_or_migration | 1.00 | 0.31 | 1 | 16 | 3116 | - |
| H11 | schema_or_migration | 0.50 | 0.23 | 1 | 13 | 3754 | src/hallpass/bookings/availability.py:119-125, src/hallpass/reports/usage.py:42-47, docs/conventions.md:38-41 |
| H12 | cross_area | 0.80 | 0.33 | 2 | 12 | 3736 | docs/runbooks/paybridge-outage.md:72-76 |
| H13 | cross_area | 0.50 | 0.27 | 1 | 11 | 3969 | src/hallpass/billing/refunds.py:111-138, docs/meetings/2024-05-14-holds-and-no-shows.md:32-40, docs/notifications/adding-a-notification.md:5-33 |
| H14 | cross_area | 0.80 | 0.31 | 1 | 13 | 3501 | src/hallpass/notifications/recipients.py:66-108 |
| H15 | superseded_trap | 0.20 | 0.11 | 1 | 9 | 2484 | src/hallpass/billing/refunds.py:73-95, src/hallpass/notifications/templates/booking_cancelled.email.txt:1-7, docs/notifications/adding-a-notification.md:9-13, src/hallpass/notifications/recipients.py:50-63 |
| H16 | superseded_trap | 0.20 | 0.08 | 1 | 12 | 2339 | docs/decisions/0011-thirty-minute-slots.md:26-41, src/hallpass/bookings/slots.py:23-34, docs/bookings/availability-search.md:62-66, tests/bookings/test_availability.py:103-122 |
| H17 | assumption_trap | 0.80 | 0.27 | 1 | 15 | 3905 | src/hallpass/billing/invoices.py:236-267 |
| H18 | assumption_trap | 1.00 | 0.33 | 1 | 15 | 3768 | - |
| H19 | missing_information | 0.40 | 0.20 | 1 | 10 | 2460 | db/migrations/0009_no_show_and_flag_rollout.sql:9-17, src/hallpass/reports/usage.py:1-9, docs/notifications/reminders.md:8-10 |
| H20 | missing_information | 0.40 | 0.17 | 1 | 12 | 3941 | docs/bookings/blackouts-and-series.md:13-30, docs/bookings/blackouts-and-series.md:49-66, src/hallpass/bookings/blackouts.py:164-167 |

Mean recall 0.57, mean precision 0.27, mean package ~3399 tokens = 0.02 of the full corpus.
Forbidden items returned: 0. Expected-unresolved misses: 2. Status mismatches: 0.

Recall by category: assumption_trap 0.90, bugfix 0.61, cross_area 0.70, feature_constrained_by_decision 0.46, missing_information 0.40, schema_or_migration 0.75, superseded_trap 0.20
