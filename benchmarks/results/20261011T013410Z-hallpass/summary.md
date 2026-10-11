# Retrieval evaluation: hallpass

- Run: `20261011T013410Z-hallpass`, commit `2d07cd5a85`
- Config: max_tokens=200000, per_kind_limit=50
- Corpus: 163 files, 1035 chunks, ~139612 tokens (estimated)

| Task | Category | Recall | Precision | First hit | Items | ~Tokens | Missed |
|---|---|---|---|---|---|---|---|
| H01 | bugfix | 1.00 | 0.06 | 2 | 129 | 29838 | - |
| H02 | bugfix | 1.00 | 0.05 | 1 | 116 | 29979 | - |
| H03 | bugfix | 1.00 | 0.04 | 1 | 115 | 33773 | - |
| H04 | bugfix | 1.00 | 0.05 | 1 | 110 | 26097 | - |
| H05 | bugfix | 1.00 | 0.04 | 1 | 121 | 29417 | - |
| H06 | feature_constrained_by_decision | 0.50 | 0.03 | 5 | 106 | 29199 | docs/notifications/adding-a-notification.md:5-33, docs/decisions/0008-transactional-outbox-for-notifications.md:24-38, src/hallpass/notifications/templates.py:20-32 |
| H07 | feature_constrained_by_decision | 0.67 | 0.02 | 1 | 191 | 43680 | src/hallpass/core/flags.py:64-94, src/hallpass/api/staff.py:140-146 |
| H08 | feature_constrained_by_decision | 1.00 | 0.04 | 1 | 138 | 33467 | - |
| H09 | feature_constrained_by_decision | 0.83 | 0.05 | 2 | 93 | 18835 | docs/accounts/roles.md:49-49 |
| H10 | schema_or_migration | 1.00 | 0.03 | 1 | 196 | 40181 | - |
| H11 | schema_or_migration | 1.00 | 0.08 | 1 | 84 | 24418 | - |
| H12 | cross_area | 1.00 | 0.04 | 2 | 119 | 31433 | - |
| H13 | cross_area | 0.83 | 0.03 | 1 | 152 | 38731 | src/hallpass/billing/refunds.py:111-138 |
| H14 | cross_area | 0.60 | 0.03 | 1 | 115 | 30705 | src/hallpass/bookings/lifecycle.py:205-213, src/hallpass/notifications/recipients.py:66-108 |
| H15 | superseded_trap | 0.40 | 0.02 | 2 | 109 | 29131 | src/hallpass/notifications/templates/booking_cancelled.email.txt:1-7, docs/notifications/adding-a-notification.md:9-13, src/hallpass/notifications/recipients.py:50-63 |
| H16 | superseded_trap | 0.80 | 0.03 | 1 | 192 | 40921 | docs/bookings/availability-search.md:62-66 |
| H17 | assumption_trap | 1.00 | 0.04 | 1 | 126 | 31822 | - |
| H18 | assumption_trap | 1.00 | 0.04 | 1 | 128 | 31092 | - |
| H19 | missing_information | 0.80 | 0.03 | 1 | 123 | 30918 | db/migrations/0009_no_show_and_flag_rollout.sql:9-17 |
| H20 | missing_information | 0.60 | 0.02 | 1 | 168 | 37316 | docs/bookings/blackouts-and-series.md:13-30, docs/bookings/blackouts-and-series.md:49-66 |

Mean recall 0.85, mean precision 0.04, mean package ~32048 tokens = 0.23 of the full corpus.
Forbidden items returned: 0. Expected-unresolved misses: 2. Status mismatches: 0.

Recall by category: assumption_trap 1.00, bugfix 1.00, cross_area 0.81, feature_constrained_by_decision 0.75, missing_information 0.70, schema_or_migration 1.00, superseded_trap 0.60
