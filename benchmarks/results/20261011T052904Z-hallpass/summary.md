# Retrieval evaluation: hallpass

- Run: `20261011T052904Z-hallpass`, commit `2cea672515`
- Config: max_tokens=4000, per_kind_limit=10, min_relative_score=0.0, max_references=0, hops=2, detail=compact, retrieval=hybrid (nomic-embed-text@0a109f422b47)
- Corpus: 163 files, 1035 chunks, ~139612 tokens (estimated)

| Task | Category | Recall | Precision | First hit | Items | ~Tokens | Missed |
|---|---|---|---|---|---|---|---|
| H01 | bugfix | 0.80 | 0.14 | 1 | 36 | 3931 | src/hallpass/bookings/recurring.py:69-95 |
| H02 | bugfix | 0.83 | 0.17 | 1 | 30 | 3392 | src/hallpass/core/db.py:126-138 |
| H03 | bugfix | 1.00 | 0.17 | 2 | 30 | 3044 | - |
| H04 | bugfix | 0.80 | 0.13 | 1 | 30 | 3344 | src/hallpass/bookings/blackouts.py:180-192 |
| H05 | bugfix | 1.00 | 0.17 | 1 | 30 | 3184 | - |
| H06 | feature_constrained_by_decision | 0.33 | 0.06 | 5 | 36 | 3942 | docs/notifications/adding-a-notification.md:5-33, docs/decisions/0008-transactional-outbox-for-notifications.md:24-38, src/hallpass/notifications/recipients.py:26-38, src/hallpass/notifications/templates.py:20-32 |
| H07 | feature_constrained_by_decision | 0.33 | 0.06 | 1 | 36 | 3978 | docs/decisions/0014-feature-flags-in-database.md:27-43, db/migrations/0007_feature_flags.sql:7-19, src/hallpass/core/flags.py:64-94, src/hallpass/api/staff.py:140-146 |
| H08 | feature_constrained_by_decision | 0.67 | 0.13 | 1 | 30 | 3358 | src/hallpass/bookings/lifecycle.py:50-54, src/hallpass/core/config.py:104-104 |
| H09 | feature_constrained_by_decision | 0.83 | 0.17 | 1 | 30 | 3254 | docs/accounts/roles.md:49-49 |
| H10 | schema_or_migration | 1.00 | 0.14 | 1 | 36 | 3982 | - |
| H11 | schema_or_migration | 0.67 | 0.15 | 1 | 33 | 3983 | src/hallpass/bookings/availability.py:119-125, src/hallpass/reports/usage.py:42-47 |
| H12 | cross_area | 1.00 | 0.17 | 1 | 30 | 3488 | - |
| H13 | cross_area | 0.67 | 0.11 | 1 | 36 | 3917 | src/hallpass/billing/refunds.py:111-138, docs/notifications/adding-a-notification.md:5-33 |
| H14 | cross_area | 0.60 | 0.10 | 1 | 30 | 3212 | src/hallpass/bookings/lifecycle.py:205-213, src/hallpass/notifications/recipients.py:66-108 |
| H15 | superseded_trap | 0.40 | 0.07 | 1 | 30 | 3187 | src/hallpass/notifications/templates/booking_cancelled.email.txt:1-7, docs/notifications/adding-a-notification.md:9-13, src/hallpass/notifications/recipients.py:50-63 |
| H16 | superseded_trap | 0.80 | 0.14 | 1 | 37 | 3987 | docs/bookings/availability-search.md:62-66 |
| H17 | assumption_trap | 1.00 | 0.14 | 1 | 36 | 3948 | - |
| H18 | assumption_trap | 1.00 | 0.14 | 1 | 35 | 3929 | - |
| H19 | missing_information | 0.60 | 0.10 | 1 | 30 | 3082 | db/migrations/0009_no_show_and_flag_rollout.sql:9-17, src/hallpass/reports/usage.py:1-9 |
| H20 | missing_information | 0.60 | 0.08 | 1 | 38 | 3972 | docs/bookings/blackouts-and-series.md:13-30, docs/bookings/blackouts-and-series.md:49-66 |

Mean recall 0.75, mean precision 0.13, mean package ~3606 tokens = 0.03 of the full corpus.
Forbidden items returned: 0. Expected-unresolved misses: 2. Status mismatches: 0.

Recall by category: assumption_trap 1.00, bugfix 0.89, cross_area 0.76, feature_constrained_by_decision 0.54, missing_information 0.60, schema_or_migration 0.83, superseded_trap 0.60
