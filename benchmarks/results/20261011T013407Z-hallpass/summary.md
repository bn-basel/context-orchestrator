# Retrieval evaluation: hallpass

- Run: `20261011T013407Z-hallpass`, commit `2d07cd5a85`
- Config: max_tokens=16000, per_kind_limit=10
- Corpus: 163 files, 1035 chunks, ~139612 tokens (estimated)

| Task | Category | Recall | Precision | First hit | Items | ~Tokens | Missed |
|---|---|---|---|---|---|---|---|
| H01 | bugfix | 0.80 | 0.15 | 2 | 40 | 10628 | src/hallpass/bookings/recurring.py:69-95 |
| H02 | bugfix | 0.83 | 0.17 | 1 | 30 | 10199 | src/hallpass/core/db.py:126-138 |
| H03 | bugfix | 0.60 | 0.10 | 1 | 30 | 9900 | src/hallpass/bookings/recurring.py:235-261, src/hallpass/bookings/lifecycle.py:178-191 |
| H04 | bugfix | 0.60 | 0.10 | 1 | 30 | 6675 | src/hallpass/bookings/blackouts.py:180-192, src/hallpass/bookings/availability.py:60-77 |
| H05 | bugfix | 1.00 | 0.17 | 1 | 30 | 8807 | - |
| H06 | feature_constrained_by_decision | 0.50 | 0.07 | 5 | 40 | 10566 | docs/notifications/adding-a-notification.md:5-33, docs/decisions/0008-transactional-outbox-for-notifications.md:24-38, src/hallpass/notifications/templates.py:20-32 |
| H07 | feature_constrained_by_decision | 0.50 | 0.06 | 1 | 50 | 11918 | docs/decisions/0014-feature-flags-in-database.md:27-43, src/hallpass/core/flags.py:64-94, src/hallpass/api/staff.py:140-146 |
| H08 | feature_constrained_by_decision | 0.83 | 0.17 | 1 | 30 | 7828 | src/hallpass/bookings/lifecycle.py:50-54 |
| H09 | feature_constrained_by_decision | 0.83 | 0.17 | 2 | 30 | 6504 | docs/accounts/roles.md:49-49 |
| H10 | schema_or_migration | 1.00 | 0.10 | 1 | 50 | 11495 | - |
| H11 | schema_or_migration | 0.67 | 0.13 | 1 | 39 | 11052 | src/hallpass/bookings/availability.py:119-125, src/hallpass/reports/usage.py:42-47 |
| H12 | cross_area | 1.00 | 0.17 | 2 | 30 | 9504 | - |
| H13 | cross_area | 0.67 | 0.10 | 1 | 40 | 10905 | src/hallpass/billing/refunds.py:111-138, docs/notifications/adding-a-notification.md:5-33 |
| H14 | cross_area | 0.60 | 0.10 | 1 | 30 | 9282 | src/hallpass/bookings/lifecycle.py:205-213, src/hallpass/notifications/recipients.py:66-108 |
| H15 | superseded_trap | 0.40 | 0.07 | 2 | 30 | 7712 | src/hallpass/notifications/templates/booking_cancelled.email.txt:1-7, docs/notifications/adding-a-notification.md:9-13, src/hallpass/notifications/recipients.py:50-63 |
| H16 | superseded_trap | 0.60 | 0.07 | 1 | 40 | 9982 | src/hallpass/bookings/slots.py:23-34, docs/bookings/availability-search.md:62-66 |
| H17 | assumption_trap | 1.00 | 0.12 | 1 | 40 | 9794 | - |
| H18 | assumption_trap | 1.00 | 0.12 | 1 | 40 | 10463 | - |
| H19 | missing_information | 0.60 | 0.10 | 1 | 30 | 6677 | db/migrations/0009_no_show_and_flag_rollout.sql:9-17, docs/notifications/reminders.md:8-10 |
| H20 | missing_information | 0.60 | 0.07 | 1 | 40 | 12233 | docs/bookings/blackouts-and-series.md:13-30, docs/bookings/blackouts-and-series.md:49-66 |

Mean recall 0.73, mean precision 0.12, mean package ~9606 tokens = 0.07 of the full corpus.
Forbidden items returned: 0. Expected-unresolved misses: 2. Status mismatches: 0.

Recall by category: assumption_trap 1.00, bugfix 0.77, cross_area 0.76, feature_constrained_by_decision 0.67, missing_information 0.60, schema_or_migration 0.83, superseded_trap 0.50
