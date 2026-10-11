# Retrieval evaluation: hallpass

- Run: `20261011T052929Z-hallpass`, commit `2cea672515`
- Config: max_tokens=4000, per_kind_limit=8, min_relative_score=0.0, max_references=0, hops=2, detail=compact, retrieval=bm25
- Corpus: 163 files, 1035 chunks, ~139612 tokens (estimated)

| Task | Category | Recall | Precision | First hit | Items | ~Tokens | Missed |
|---|---|---|---|---|---|---|---|
| H01 | bugfix | 0.80 | 0.22 | 1 | 32 | 3468 | src/hallpass/core/tz.py:42-50 |
| H02 | bugfix | 0.83 | 0.21 | 1 | 24 | 2688 | src/hallpass/core/db.py:126-138 |
| H03 | bugfix | 0.60 | 0.12 | 1 | 24 | 2632 | src/hallpass/bookings/recurring.py:235-261, src/hallpass/bookings/lifecycle.py:178-191 |
| H04 | bugfix | 0.80 | 0.18 | 1 | 22 | 2417 | src/hallpass/bookings/blackouts.py:180-192 |
| H05 | bugfix | 0.80 | 0.17 | 1 | 24 | 2432 | src/hallpass/billing/refunds.py:163-170 |
| H06 | feature_constrained_by_decision | 0.33 | 0.06 | 6 | 32 | 3540 | docs/notifications/adding-a-notification.md:5-33, docs/decisions/0008-transactional-outbox-for-notifications.md:24-38, src/hallpass/notifications/recipients.py:26-38, src/hallpass/notifications/templates.py:20-32 |
| H07 | feature_constrained_by_decision | 0.33 | 0.05 | 1 | 38 | 3891 | docs/decisions/0014-feature-flags-in-database.md:27-43, db/migrations/0007_feature_flags.sql:7-19, src/hallpass/core/flags.py:64-94, src/hallpass/api/staff.py:140-146 |
| H08 | feature_constrained_by_decision | 0.83 | 0.21 | 1 | 24 | 2446 | src/hallpass/bookings/lifecycle.py:50-54 |
| H09 | feature_constrained_by_decision | 0.83 | 0.21 | 2 | 24 | 2635 | docs/accounts/roles.md:49-49 |
| H10 | schema_or_migration | 1.00 | 0.14 | 1 | 36 | 3958 | - |
| H11 | schema_or_migration | 0.67 | 0.16 | 1 | 32 | 3811 | src/hallpass/bookings/availability.py:119-125, src/hallpass/reports/usage.py:42-47 |
| H12 | cross_area | 1.00 | 0.21 | 1 | 24 | 2657 | - |
| H13 | cross_area | 0.67 | 0.12 | 1 | 32 | 3525 | src/hallpass/billing/refunds.py:111-138, docs/notifications/adding-a-notification.md:5-33 |
| H14 | cross_area | 0.60 | 0.12 | 1 | 24 | 2673 | src/hallpass/bookings/lifecycle.py:205-213, src/hallpass/notifications/recipients.py:66-108 |
| H15 | superseded_trap | 0.40 | 0.08 | 1 | 24 | 2548 | src/hallpass/notifications/templates/booking_cancelled.email.txt:1-7, docs/notifications/adding-a-notification.md:9-13, src/hallpass/notifications/recipients.py:50-63 |
| H16 | superseded_trap | 0.80 | 0.12 | 1 | 32 | 3367 | docs/bookings/availability-search.md:62-66 |
| H17 | assumption_trap | 1.00 | 0.16 | 1 | 32 | 3559 | - |
| H18 | assumption_trap | 0.80 | 0.12 | 2 | 32 | 3569 | src/hallpass/accounts/consents.py:8-35 |
| H19 | missing_information | 0.40 | 0.08 | 1 | 24 | 2547 | db/migrations/0009_no_show_and_flag_rollout.sql:9-17, src/hallpass/reports/usage.py:1-9, docs/notifications/reminders.md:8-10 |
| H20 | missing_information | 0.60 | 0.09 | 1 | 32 | 3256 | docs/bookings/blackouts-and-series.md:13-30, docs/bookings/blackouts-and-series.md:49-66 |

Mean recall 0.70, mean precision 0.14, mean package ~3081 tokens = 0.02 of the full corpus.
Forbidden items returned: 0. Expected-unresolved misses: 2. Status mismatches: 0.

Recall by category: assumption_trap 0.90, bugfix 0.77, cross_area 0.76, feature_constrained_by_decision 0.58, missing_information 0.50, schema_or_migration 0.83, superseded_trap 0.60
