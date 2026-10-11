# Retrieval evaluation: sample_project

- Run: `20261011T004023Z-sample_project`, commit `4c38806717`
- Config: max_tokens=4000, per_kind_limit=3
- Corpus: 18 files, 57 chunks, ~2645 tokens (estimated)

| Task | Category | Recall | Precision | First hit | Items | ~Tokens | Missed |
|---|---|---|---|---|---|---|---|
| T01 | bugfix | 1.00 | 0.36 | 1 | 11 | 947 | - |
| T02 | bugfix | 0.75 | 0.38 | 1 | 8 | 761 | src/shelfwise/fines.py:12-15 |
| T03 | adr_constrained_feature | 0.50 | 0.25 | 1 | 8 | 653 | docs/decisions/0004-store-money-as-integer-cents.md:13-16, docs/conventions.md:13-15 |
| T04 | schema | 1.00 | 0.67 | 1 | 6 | 487 | - |
| T05 | superseded_trap | 1.00 | 0.43 | 2 | 7 | 591 | - |
| T06 | assumption_trap | 1.00 | 0.44 | 1 | 9 | 675 | - |
| T07 | vocabulary_mismatch | 0.25 | 0.50 | 1 | 2 | 157 | docs/constraints.md:11-12, src/shelfwise/loans.py:32-40, src/shelfwise/fines.py:12-15 |
| T08 | conventions | 1.00 | 0.22 | 1 | 9 | 633 | - |
| T09 | missing_information | 1.00 | 0.33 | 1 | 3 | 279 | - |

Mean recall 0.83, mean precision 0.40, mean package ~576 tokens = 0.22 of the full corpus.
Forbidden items returned: 0. Expected-unresolved misses: 0. Status mismatches: 0.

Recall by category: adr_constrained_feature 0.50, assumption_trap 1.00, bugfix 0.88, conventions 1.00, missing_information 1.00, schema 1.00, superseded_trap 1.00, vocabulary_mismatch 0.25

## gate1: PASSED

| Criterion | Metric | Target | Actual | Result |
|---|---|---|---|---|
| C1 | mean_recall | >= 0.8 | 0.83 | pass |
| C2 | forbidden_returned | == 0 | 0 | pass |
| C3 | unresolved_misses | == 0 | 0 | pass |
| C4 | status_mismatches | == 0 | 0 | pass |
| C5 | mean_package_to_corpus_ratio | <= 0.5 | 0.22 | pass |
