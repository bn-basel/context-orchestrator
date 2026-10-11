# Retrieval evaluation: hallpass

- Run: `20261011T025040Z-hallpass`, commit `3e4131f828`
- Config: max_tokens=4000, per_kind_limit=3, min_relative_score=0.0, max_references=0, hops=2, retrieval=bm25
- Corpus: 163 files, 1035 chunks, ~139612 tokens (estimated)

| Task | Category | Recall | Precision | First hit | Items | ~Tokens | Missed |
|---|---|---|---|---|---|---|---|
| H01 | bugfix | 0.40 | 0.20 | 1 | 10 | 3946 | src/hallpass/bookings/recurring.py:69-95, src/hallpass/core/tz.py:42-50, docs/bookings/time-and-dst.md:8-17 |
| H02 | bugfix | 0.83 | 0.62 | 1 | 8 | 3609 | src/hallpass/core/db.py:126-138 |
| H03 | bugfix | 0.60 | 0.33 | 1 | 9 | 3274 | src/hallpass/bookings/recurring.py:235-261, src/hallpass/bookings/lifecycle.py:178-191 |
| H04 | bugfix | 0.20 | 0.11 | 1 | 9 | 2531 | src/hallpass/reports/usage.py:49-57, db/migrations/0010_release_3_2.sql:44-47, src/hallpass/bookings/blackouts.py:180-192, src/hallpass/bookings/availability.py:60-77 |
| H05 | bugfix | 0.60 | 0.33 | 1 | 9 | 2468 | src/hallpass/billing/refunds.py:163-170, tests/billing/test_refunds.py:47-58 |
| H06 | feature_constrained_by_decision | 0.33 | 0.17 | 7 | 12 | 2940 | docs/notifications/adding-a-notification.md:5-33, docs/decisions/0008-transactional-outbox-for-notifications.md:24-38, src/hallpass/notifications/recipients.py:26-38, src/hallpass/notifications/templates.py:20-32 |
| H07 | feature_constrained_by_decision | 0.17 | 0.07 | 11 | 15 | 3244 | docs/runbooks/paybridge-outage.md:23-28, docs/decisions/0014-feature-flags-in-database.md:27-43, db/migrations/0007_feature_flags.sql:7-19, src/hallpass/core/flags.py:64-94, src/hallpass/api/staff.py:140-146 |
| H08 | feature_constrained_by_decision | 0.33 | 0.22 | 1 | 9 | 2177 | docs/meetings/2024-05-14-holds-and-no-shows.md:25-30, src/hallpass/bookings/lifecycle.py:50-54, src/hallpass/core/config.py:104-104, docs/bookings/holds-and-payment.md:26-31 |
| H09 | feature_constrained_by_decision | 0.67 | 0.44 | 2 | 9 | 1821 | docs/constraints.md:28-30, docs/accounts/roles.md:49-49 |
| H10 | schema_or_migration | 1.00 | 0.33 | 1 | 15 | 3092 | - |
| H11 | schema_or_migration | 0.50 | 0.36 | 1 | 11 | 3905 | src/hallpass/bookings/availability.py:119-125, src/hallpass/reports/usage.py:42-47, docs/conventions.md:38-41 |
| H12 | cross_area | 0.80 | 0.44 | 1 | 9 | 3094 | src/hallpass/billing/reconciliation.py:97-125 |
| H13 | cross_area | 0.33 | 0.17 | 1 | 12 | 3980 | src/hallpass/billing/payments.py:171-187, src/hallpass/billing/refunds.py:111-138, docs/meetings/2024-05-14-holds-and-no-shows.md:32-40, docs/notifications/adding-a-notification.md:5-33 |
| H14 | cross_area | 0.60 | 0.33 | 1 | 9 | 2455 | src/hallpass/bookings/lifecycle.py:205-213, src/hallpass/notifications/recipients.py:66-108 |
| H15 | superseded_trap | 0.20 | 0.11 | 1 | 9 | 2484 | src/hallpass/billing/refunds.py:73-95, src/hallpass/notifications/templates/booking_cancelled.email.txt:1-7, docs/notifications/adding-a-notification.md:9-13, src/hallpass/notifications/recipients.py:50-63 |
| H16 | superseded_trap | 0.40 | 0.17 | 1 | 12 | 2929 | src/hallpass/bookings/slots.py:23-34, docs/bookings/availability-search.md:62-66, tests/bookings/test_availability.py:103-122 |
| H17 | assumption_trap | 1.00 | 0.45 | 1 | 11 | 3960 | - |
| H18 | assumption_trap | 0.60 | 0.25 | 1 | 12 | 2767 | docs/notifications/reminders.md:26-46, src/hallpass/accounts/consents.py:8-35 |
| H19 | missing_information | 0.40 | 0.22 | 1 | 9 | 2485 | db/migrations/0009_no_show_and_flag_rollout.sql:9-17, src/hallpass/reports/usage.py:1-9, docs/notifications/reminders.md:8-10 |
| H20 | missing_information | 0.60 | 0.30 | 1 | 10 | 3846 | docs/bookings/blackouts-and-series.md:13-30, docs/bookings/blackouts-and-series.md:49-66 |

Mean recall 0.53, mean precision 0.28, mean package ~3050 tokens = 0.02 of the full corpus.
Forbidden items returned: 0. Expected-unresolved misses: 2. Status mismatches: 0.

Recall by category: assumption_trap 0.80, bugfix 0.53, cross_area 0.58, feature_constrained_by_decision 0.38, missing_information 0.50, schema_or_migration 0.75, superseded_trap 0.30

## gate1: NOT PASSED

| Criterion | Metric | Target | Actual | Result |
|---|---|---|---|---|
| C1 | mean_recall | >= 0.8 | 0.53 | FAIL |
| C2 | forbidden_returned | == 0 | 0 | pass |
| C3 | unresolved_misses | == 0 | 2 | FAIL |
| C4 | status_mismatches | == 0 | 0 | pass |
| C5 | mean_package_to_corpus_ratio | <= 0.5 | 0.02 | pass |
