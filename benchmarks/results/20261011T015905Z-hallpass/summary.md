# Retrieval evaluation: hallpass

- Run: `20261011T015905Z-hallpass`, commit `e34952cd43`
- Config: max_tokens=4000, per_kind_limit=3, min_relative_score=0.5
- Corpus: 163 files, 1035 chunks, ~139612 tokens (estimated)

| Task | Category | Recall | Precision | First hit | Items | ~Tokens | Missed |
|---|---|---|---|---|---|---|---|
| H01 | bugfix | 0.40 | 0.20 | 2 | 10 | 3218 | src/hallpass/bookings/recurring.py:69-95, src/hallpass/core/tz.py:42-50, docs/bookings/time-and-dst.md:8-17 |
| H02 | bugfix | 0.67 | 0.57 | 1 | 7 | 3304 | src/hallpass/bookings/waitlist.py:105-124, src/hallpass/core/db.py:126-138 |
| H03 | bugfix | 0.60 | 0.43 | 1 | 7 | 2610 | src/hallpass/bookings/recurring.py:235-261, src/hallpass/bookings/lifecycle.py:178-191 |
| H04 | bugfix | 0.40 | 0.29 | 1 | 7 | 2058 | db/migrations/0010_release_3_2.sql:44-47, src/hallpass/bookings/blackouts.py:180-192, src/hallpass/bookings/availability.py:60-77 |
| H05 | bugfix | 0.40 | 1.00 | 1 | 2 | 794 | src/hallpass/billing/refunds.py:163-170, src/hallpass/api/bookings.py:77-85, tests/billing/test_refunds.py:47-58 |
| H06 | feature_constrained_by_decision | 0.17 | 0.33 | 3 | 3 | 573 | src/hallpass/accounts/organisations.py:56-70, docs/notifications/adding-a-notification.md:5-33, docs/decisions/0008-transactional-outbox-for-notifications.md:24-38, src/hallpass/notifications/recipients.py:26-38, src/hallpass/notifications/templates.py:20-32 |
| H07 | feature_constrained_by_decision | 0.17 | 1.00 | 1 | 1 | 371 | docs/decisions/0014-feature-flags-in-database.md:27-43, docs/conventions.md:80-86, db/migrations/0007_feature_flags.sql:7-19, src/hallpass/core/flags.py:64-94, src/hallpass/api/staff.py:140-146 |
| H08 | feature_constrained_by_decision | 0.67 | 0.57 | 1 | 7 | 1940 | src/hallpass/bookings/lifecycle.py:50-54, src/hallpass/core/config.py:104-104 |
| H09 | feature_constrained_by_decision | 0.50 | 0.38 | 2 | 8 | 1660 | docs/constraints.md:28-30, docs/constraints.md:55-60, docs/accounts/roles.md:49-49 |
| H10 | schema_or_migration | 0.80 | 0.44 | 1 | 9 | 1761 | db/migrations/0010_release_3_2.sql:21-24 |
| H11 | schema_or_migration | 0.33 | 1.00 | 1 | 2 | 1183 | db/migrations/0002_facilities.sql:31-41, src/hallpass/bookings/availability.py:119-125, src/hallpass/reports/usage.py:42-47, docs/conventions.md:38-41 |
| H12 | cross_area | 0.60 | 0.38 | 2 | 8 | 3385 | src/hallpass/worker.py:123-129, docs/runbooks/paybridge-outage.md:72-76 |
| H13 | cross_area | 0.50 | 0.60 | 1 | 5 | 1966 | src/hallpass/bookings/lifecycle.py:230-247, src/hallpass/billing/refunds.py:111-138, docs/notifications/adding-a-notification.md:5-33 |
| H14 | cross_area | 0.60 | 0.50 | 1 | 6 | 1099 | src/hallpass/bookings/lifecycle.py:205-213, src/hallpass/notifications/recipients.py:66-108 |
| H15 | superseded_trap | 0.20 | 0.12 | 2 | 8 | 2814 | src/hallpass/billing/refunds.py:73-95, src/hallpass/notifications/templates/booking_cancelled.email.txt:1-7, docs/notifications/adding-a-notification.md:9-13, src/hallpass/notifications/recipients.py:50-63 |
| H16 | superseded_trap | 0.20 | 0.11 | 1 | 9 | 1907 | docs/decisions/0011-thirty-minute-slots.md:26-41, src/hallpass/bookings/slots.py:23-34, docs/bookings/availability-search.md:62-66, tests/bookings/test_availability.py:103-122 |
| H17 | assumption_trap | 0.60 | 0.43 | 1 | 7 | 1787 | src/hallpass/billing/invoices.py:236-267, docs/known-issues/billing.md:41-46 |
| H18 | assumption_trap | 1.00 | 0.45 | 1 | 11 | 2828 | - |
| H19 | missing_information | 0.40 | 0.40 | 1 | 5 | 1173 | db/migrations/0009_no_show_and_flag_rollout.sql:9-17, src/hallpass/reports/usage.py:1-9, docs/notifications/reminders.md:8-10 |
| H20 | missing_information | 0.40 | 0.22 | 1 | 9 | 3759 | docs/bookings/blackouts-and-series.md:13-30, docs/bookings/blackouts-and-series.md:49-66, src/hallpass/bookings/blackouts.py:164-167 |

Mean recall 0.48, mean precision 0.47, mean package ~2010 tokens = 0.01 of the full corpus.
Forbidden items returned: 0. Expected-unresolved misses: 1. Status mismatches: 0.

Recall by category: assumption_trap 0.80, bugfix 0.49, cross_area 0.57, feature_constrained_by_decision 0.38, missing_information 0.40, schema_or_migration 0.57, superseded_trap 0.20
