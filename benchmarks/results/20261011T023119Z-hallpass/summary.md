# Retrieval evaluation: hallpass

- Run: `20261011T023119Z-hallpass`, commit `ef91312d19`
- Config: max_tokens=4000, per_kind_limit=3, min_relative_score=0.0, max_references=0, retrieval=semantic (nomic-embed-text@0a109f422b47)
- Corpus: 163 files, 1035 chunks, ~139612 tokens (estimated)

| Task | Category | Recall | Precision | First hit | Items | ~Tokens | Missed |
|---|---|---|---|---|---|---|---|
| H01 | bugfix | 0.40 | 0.30 | 1 | 10 | 3842 | src/hallpass/bookings/recurring.py:69-95, src/hallpass/core/tz.py:42-50, tests/bookings/test_recurring.py:63-85 |
| H02 | bugfix | 0.67 | 0.44 | 1 | 9 | 3912 | src/hallpass/bookings/waitlist.py:105-124, src/hallpass/core/db.py:126-138 |
| H03 | bugfix | 0.60 | 0.38 | 4 | 8 | 3850 | src/hallpass/bookings/recurring.py:235-261, src/hallpass/bookings/lifecycle.py:178-191 |
| H04 | bugfix | 0.40 | 0.22 | 1 | 9 | 3083 | src/hallpass/reports/usage.py:75-98, db/migrations/0010_release_3_2.sql:44-47, src/hallpass/bookings/blackouts.py:180-192 |
| H05 | bugfix | 0.40 | 0.22 | 1 | 9 | 2272 | src/hallpass/billing/refunds.py:163-170, src/hallpass/api/bookings.py:77-85, tests/billing/test_refunds.py:47-58 |
| H06 | feature_constrained_by_decision | 0.33 | 0.17 | 5 | 12 | 2107 | docs/notifications/adding-a-notification.md:5-33, docs/decisions/0008-transactional-outbox-for-notifications.md:24-38, src/hallpass/notifications/recipients.py:26-38, src/hallpass/notifications/templates.py:20-32 |
| H07 | feature_constrained_by_decision | 0.33 | 0.13 | 2 | 15 | 3437 | docs/decisions/0014-feature-flags-in-database.md:27-43, db/migrations/0007_feature_flags.sql:7-19, src/hallpass/core/flags.py:64-94, src/hallpass/api/staff.py:140-146 |
| H08 | feature_constrained_by_decision | 0.50 | 0.33 | 2 | 9 | 2819 | docs/decisions/0014-feature-flags-in-database.md:41-43, src/hallpass/core/config.py:104-104, docs/bookings/holds-and-payment.md:26-31 |
| H09 | feature_constrained_by_decision | 0.17 | 0.11 | 2 | 9 | 1579 | docs/decisions/0010-personal-data-retention.md:22-40, src/hallpass/accounts/retention.py:62-80, docs/constraints.md:28-30, docs/constraints.md:55-60, docs/accounts/roles.md:49-49 |
| H10 | schema_or_migration | 1.00 | 0.33 | 3 | 15 | 2976 | - |
| H11 | schema_or_migration | 0.50 | 0.33 | 2 | 12 | 3780 | src/hallpass/bookings/availability.py:119-125, src/hallpass/reports/usage.py:42-47, docs/conventions.md:38-41 |
| H12 | cross_area | 0.80 | 0.44 | 1 | 9 | 2719 | src/hallpass/billing/reconciliation.py:143-162 |
| H13 | cross_area | 0.33 | 0.17 | 3 | 12 | 3227 | src/hallpass/billing/payments.py:171-187, src/hallpass/bookings/lifecycle.py:230-247, src/hallpass/billing/refunds.py:111-138, docs/notifications/adding-a-notification.md:5-33 |
| H14 | cross_area | 0.60 | 0.33 | 1 | 9 | 2741 | src/hallpass/bookings/lifecycle.py:205-213, src/hallpass/notifications/recipients.py:66-108 |
| H15 | superseded_trap | 0.20 | 0.11 | 1 | 9 | 2750 | src/hallpass/billing/refunds.py:73-95, src/hallpass/notifications/templates/booking_cancelled.email.txt:1-7, docs/notifications/adding-a-notification.md:9-13, src/hallpass/notifications/recipients.py:50-63 |
| H16 | superseded_trap | 0.60 | 0.25 | 5 | 12 | 2865 | docs/bookings/availability-search.md:62-66, tests/bookings/test_availability.py:103-122 |
| H17 | assumption_trap | 0.80 | 0.33 | 1 | 12 | 3562 | src/hallpass/billing/invoices.py:236-267 |
| H18 | assumption_trap | 0.60 | 0.25 | 1 | 12 | 3368 | docs/notifications/adding-a-notification.md:14-17, src/hallpass/accounts/consents.py:8-35 |
| H19 | missing_information | 0.40 | 0.22 | 2 | 9 | 2054 | db/migrations/0009_no_show_and_flag_rollout.sql:9-17, src/hallpass/reports/usage.py:1-9, docs/notifications/reminders.md:8-10 |
| H20 | missing_information | 0.40 | 0.18 | 3 | 11 | 3660 | docs/bookings/blackouts-and-series.md:13-30, docs/bookings/blackouts-and-series.md:49-66, src/hallpass/bookings/blackouts.py:164-167 |

Mean recall 0.50, mean precision 0.26, mean package ~3030 tokens = 0.02 of the full corpus.
Forbidden items returned: 0. Expected-unresolved misses: 2. Status mismatches: 0.

Recall by category: assumption_trap 0.70, bugfix 0.49, cross_area 0.58, feature_constrained_by_decision 0.33, missing_information 0.40, schema_or_migration 0.75, superseded_trap 0.40

## gate1: NOT PASSED

| Criterion | Metric | Target | Actual | Result |
|---|---|---|---|---|
| C1 | mean_recall | >= 0.8 | 0.50 | FAIL |
| C2 | forbidden_returned | == 0 | 0 | pass |
| C3 | unresolved_misses | == 0 | 2 | FAIL |
| C4 | status_mismatches | == 0 | 0 | pass |
| C5 | mean_package_to_corpus_ratio | <= 0.5 | 0.02 | pass |
