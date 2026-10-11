# Retrieval evaluation: sample_project

- Run: `20261011T015903Z-sample_project`, commit `e34952cd43`
- Config: max_tokens=4000, per_kind_limit=3, min_relative_score=0.4
- Corpus: 18 files, 57 chunks, ~2645 tokens (estimated)

| Task | Category | Recall | Precision | First hit | Items | ~Tokens | Missed |
|---|---|---|---|---|---|---|---|
| T01 | bugfix | 0.50 | 1.00 | 1 | 2 | 327 | docs/decisions/0003-timestamps-in-utc.md:8-11, tests/test_fines.py:19-21 |
| T02 | bugfix | 0.50 | 1.00 | 1 | 2 | 240 | src/shelfwise/fines.py:12-15, db/schema.sql:18-26 |
| T03 | adr_constrained_feature | 0.25 | 0.25 | 1 | 4 | 405 | docs/decisions/0004-store-money-as-integer-cents.md:13-16, docs/decisions/0004-store-money-as-integer-cents.md:18-20, docs/conventions.md:13-15 |
| T04 | schema | 1.00 | 0.80 | 1 | 5 | 420 | - |
| T05 | superseded_trap | 0.33 | 0.50 | 2 | 2 | 207 | docs/decisions/0004-store-money-as-integer-cents.md:13-16, db/schema.sql:28-33 |
| T06 | assumption_trap | 0.50 | 1.00 | 1 | 2 | 246 | src/shelfwise/loans.py:11-12, tests/test_loans.py:16-18 |
| T07 | vocabulary_mismatch | 0.25 | 0.50 | 1 | 2 | 158 | docs/constraints.md:11-12, src/shelfwise/loans.py:32-40, src/shelfwise/fines.py:12-15 |
| T08 | conventions | 1.00 | 0.25 | 1 | 8 | 565 | - |
| T09 | missing_information | 1.00 | 1.00 | 1 | 1 | 132 | - |

Mean recall 0.59, mean precision 0.70, mean package ~300 tokens = 0.11 of the full corpus.
Forbidden items returned: 0. Expected-unresolved misses: 0. Status mismatches: 0.

Recall by category: adr_constrained_feature 0.25, assumption_trap 0.50, bugfix 0.50, conventions 1.00, missing_information 1.00, schema 1.00, superseded_trap 0.33, vocabulary_mismatch 0.25
