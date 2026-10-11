# Retrieval evaluation: sample_project

- Run: `20261011T020213Z-sample_project`, commit `2ab4c2db8d`
- Config: max_tokens=4000, per_kind_limit=3, min_relative_score=0.0, max_references=4
- Corpus: 18 files, 57 chunks, ~2645 tokens (estimated)

| Task | Category | Recall | Precision | First hit | Items | ~Tokens | Missed |
|---|---|---|---|---|---|---|---|
| T01 | bugfix | 1.00 | 0.29 | 1 | 14 | 1232 | - |
| T02 | bugfix | 0.75 | 0.38 | 1 | 8 | 761 | src/shelfwise/fines.py:12-15 |
| T03 | adr_constrained_feature | 0.50 | 0.20 | 1 | 10 | 768 | docs/decisions/0004-store-money-as-integer-cents.md:13-16, docs/conventions.md:13-15 |
| T04 | schema | 1.00 | 0.67 | 1 | 6 | 487 | - |
| T05 | superseded_trap | 1.00 | 0.43 | 2 | 7 | 592 | - |
| T06 | assumption_trap | 1.00 | 0.36 | 1 | 11 | 823 | - |
| T07 | vocabulary_mismatch | 0.00 | n/a | none | 0 | 96 | docs/assumptions.md:11-13, docs/constraints.md:11-12, src/shelfwise/loans.py:32-40, src/shelfwise/fines.py:12-15 |
| T08 | conventions | 1.00 | 0.15 | 1 | 13 | 1036 | - |
| T09 | missing_information | 1.00 | 0.33 | 1 | 3 | 280 | - |

Mean recall 0.81, mean precision 0.35, mean package ~675 tokens = 0.26 of the full corpus.
Forbidden items returned: 0. Expected-unresolved misses: 0. Status mismatches: 0.

Recall by category: adr_constrained_feature 0.50, assumption_trap 1.00, bugfix 0.88, conventions 1.00, missing_information 1.00, schema 1.00, superseded_trap 1.00, vocabulary_mismatch 0.00
