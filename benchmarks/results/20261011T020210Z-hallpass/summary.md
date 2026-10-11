# Retrieval evaluation: hallpass

- Run: `20261011T020210Z-hallpass`, commit `2ab4c2db8d`
- Config: max_tokens=4000, per_kind_limit=3, min_relative_score=0.0, max_references=4
- Corpus: 163 files, 1035 chunks, ~139612 tokens (estimated)

| Task | Category | Recall | Precision | First hit | Items | ~Tokens | Missed |
|---|---|---|---|---|---|---|---|
| H01 | bugfix | 0.60 | 0.21 | 2 | 14 | 3981 | src/hallpass/bookings/recurring.py:69-95, src/hallpass/core/tz.py:42-50 |
| H02 | bugfix | 0.67 | 0.44 | 1 | 9 | 3973 | src/hallpass/bookings/waitlist.py:105-124, src/hallpass/core/db.py:126-138 |
| H03 | bugfix | 0.60 | 0.23 | 1 | 13 | 3862 | src/hallpass/bookings/recurring.py:235-261, src/hallpass/bookings/lifecycle.py:178-191 |
| H04 | bugfix | 0.60 | 0.25 | 1 | 12 | 3210 | src/hallpass/bookings/blackouts.py:180-192, src/hallpass/bookings/availability.py:60-77 |
| H05 | bugfix | 0.60 | 0.25 | 1 | 12 | 3992 | src/hallpass/billing/refunds.py:163-170, src/hallpass/api/bookings.py:77-85 |
| H06 | feature_constrained_by_decision | 0.17 | 0.06 | 6 | 16 | 3368 | src/hallpass/accounts/organisations.py:56-70, docs/notifications/adding-a-notification.md:5-33, docs/decisions/0008-transactional-outbox-for-notifications.md:24-38, src/hallpass/notifications/recipients.py:26-38, src/hallpass/notifications/templates.py:20-32 |
| H07 | feature_constrained_by_decision | 0.17 | 0.06 | 1 | 17 | 3945 | docs/decisions/0014-feature-flags-in-database.md:27-43, docs/conventions.md:80-86, db/migrations/0007_feature_flags.sql:7-19, src/hallpass/core/flags.py:64-94, src/hallpass/api/staff.py:140-146 |
| H08 | feature_constrained_by_decision | 0.67 | 0.31 | 1 | 13 | 3743 | src/hallpass/bookings/lifecycle.py:50-54, src/hallpass/core/config.py:104-104 |
| H09 | feature_constrained_by_decision | 0.67 | 0.31 | 2 | 13 | 2232 | docs/constraints.md:28-30, docs/accounts/roles.md:49-49 |
| H10 | schema_or_migration | 1.00 | 0.26 | 1 | 19 | 3418 | - |
| H11 | schema_or_migration | 0.50 | 0.23 | 1 | 13 | 3943 | src/hallpass/bookings/availability.py:119-125, src/hallpass/reports/usage.py:42-47, docs/conventions.md:38-41 |
| H12 | cross_area | 0.60 | 0.27 | 2 | 11 | 3992 | src/hallpass/worker.py:123-129, docs/runbooks/paybridge-outage.md:72-76 |
| H13 | cross_area | 0.50 | 0.20 | 1 | 15 | 3954 | src/hallpass/bookings/lifecycle.py:230-247, src/hallpass/billing/refunds.py:111-138, docs/notifications/adding-a-notification.md:5-33 |
| H14 | cross_area | 0.60 | 0.23 | 1 | 13 | 3095 | src/hallpass/bookings/lifecycle.py:205-213, src/hallpass/notifications/recipients.py:66-108 |
| H15 | superseded_trap | 0.20 | 0.08 | 1 | 13 | 3516 | src/hallpass/billing/refunds.py:73-95, src/hallpass/notifications/templates/booking_cancelled.email.txt:1-7, docs/notifications/adding-a-notification.md:9-13, src/hallpass/notifications/recipients.py:50-63 |
| H16 | superseded_trap | 0.20 | 0.06 | 1 | 16 | 2944 | docs/decisions/0011-thirty-minute-slots.md:26-41, src/hallpass/bookings/slots.py:23-34, docs/bookings/availability-search.md:62-66, tests/bookings/test_availability.py:103-122 |
| H17 | assumption_trap | 0.80 | 0.27 | 1 | 15 | 3886 | src/hallpass/billing/invoices.py:236-267 |
| H18 | assumption_trap | 1.00 | 0.33 | 1 | 15 | 3770 | - |
| H19 | missing_information | 0.40 | 0.15 | 1 | 13 | 2761 | db/migrations/0009_no_show_and_flag_rollout.sql:9-17, src/hallpass/reports/usage.py:1-9, docs/notifications/reminders.md:8-10 |
| H20 | missing_information | 0.60 | 0.30 | 1 | 10 | 3962 | docs/bookings/blackouts-and-series.md:13-30, docs/bookings/blackouts-and-series.md:49-66 |

Mean recall 0.56, mean precision 0.23, mean package ~3577 tokens = 0.03 of the full corpus.
Forbidden items returned: 0. Expected-unresolved misses: 2. Status mismatches: 0.

Recall by category: assumption_trap 0.90, bugfix 0.61, cross_area 0.57, feature_constrained_by_decision 0.42, missing_information 0.50, schema_or_migration 0.75, superseded_trap 0.20
