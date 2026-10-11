# Retrieval evaluation: sample_project

- Run: `20261011T052923Z-sample_project`, commit `2cea672515`
- Config: max_tokens=4000, per_kind_limit=3, min_relative_score=0.0, max_references=0, hops=2, detail=full, retrieval=hybrid (nomic-embed-text@0a109f422b47)
- Corpus: 18 files, 57 chunks, ~2645 tokens (estimated)

| Task | Category | Recall | Precision | First hit | Items | ~Tokens | Missed |
|---|---|---|---|---|---|---|---|
| T01 | bugfix | 1.00 | 0.36 | 1 | 11 | 932 | - |
| T02 | bugfix | 0.75 | 0.38 | 1 | 8 | 722 | src/shelfwise/fines.py:12-15 |
| T03 | adr_constrained_feature | 1.00 | 0.44 | 1 | 9 | 636 | - |
| T04 | schema | 1.00 | 0.67 | 1 | 6 | 487 | - |
| T05 | superseded_trap | 1.00 | 0.33 | 1 | 9 | 693 | - |
| T06 | assumption_trap | 1.00 | 0.44 | 1 | 9 | 690 | - |
| T07 | vocabulary_mismatch | 0.75 | 0.50 | 2 | 6 | 455 | src/shelfwise/fines.py:12-15 |
| T08 | conventions | 1.00 | 0.22 | 1 | 9 | 634 | - |
| T09 | missing_information | 1.00 | 0.33 | 1 | 3 | 300 | - |

Mean recall 0.94, mean precision 0.41, mean package ~617 tokens = 0.23 of the full corpus.
Forbidden items returned: 0. Expected-unresolved misses: 0. Status mismatches: 0.

Recall by category: adr_constrained_feature 1.00, assumption_trap 1.00, bugfix 0.88, conventions 1.00, missing_information 1.00, schema 1.00, superseded_trap 1.00, vocabulary_mismatch 0.75
