# Retrieval evaluation: sample_project

- Run: `20261011T015851Z-sample_project`, commit `e34952cd43`
- Config: max_tokens=4000, per_kind_limit=3, min_relative_score=0.1
- Corpus: 18 files, 57 chunks, ~2645 tokens (estimated)

| Task | Category | Recall | Precision | First hit | Items | ~Tokens | Missed |
|---|---|---|---|---|---|---|---|
| T01 | bugfix | 0.75 | 0.38 | 1 | 8 | 747 | docs/decisions/0003-timestamps-in-utc.md:8-11 |
| T02 | bugfix | 0.50 | 0.40 | 1 | 5 | 579 | src/shelfwise/fines.py:12-15, db/schema.sql:18-26 |
| T03 | adr_constrained_feature | 0.50 | 0.33 | 1 | 6 | 509 | docs/decisions/0004-store-money-as-integer-cents.md:13-16, docs/conventions.md:13-15 |
| T04 | schema | 1.00 | 0.67 | 1 | 6 | 487 | - |
| T05 | superseded_trap | 0.67 | 0.50 | 2 | 4 | 409 | db/schema.sql:28-33 |
| T06 | assumption_trap | 1.00 | 0.67 | 1 | 6 | 514 | - |
| T07 | vocabulary_mismatch | 0.25 | 0.50 | 1 | 2 | 158 | docs/constraints.md:11-12, src/shelfwise/loans.py:32-40, src/shelfwise/fines.py:12-15 |
| T08 | conventions | 1.00 | 0.22 | 1 | 9 | 634 | - |
| T09 | missing_information | 1.00 | 0.50 | 1 | 2 | 207 | - |

Mean recall 0.74, mean precision 0.46, mean package ~472 tokens = 0.18 of the full corpus.
Forbidden items returned: 0. Expected-unresolved misses: 0. Status mismatches: 0.

Recall by category: adr_constrained_feature 0.50, assumption_trap 1.00, bugfix 0.62, conventions 1.00, missing_information 1.00, schema 1.00, superseded_trap 0.67, vocabulary_mismatch 0.25
