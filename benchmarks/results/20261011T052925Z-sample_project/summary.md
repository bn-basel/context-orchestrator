# Retrieval evaluation: sample_project

- Run: `20261011T052925Z-sample_project`, commit `2cea672515`
- Config: max_tokens=4000, per_kind_limit=8, min_relative_score=0.0, max_references=0, hops=2, detail=compact, retrieval=hybrid (nomic-embed-text@0a109f422b47)
- Corpus: 18 files, 57 chunks, ~2645 tokens (estimated)

| Task | Category | Recall | Precision | First hit | Items | ~Tokens | Missed |
|---|---|---|---|---|---|---|---|
| T01 | bugfix | 1.00 | 0.15 | 1 | 26 | 2003 | - |
| T02 | bugfix | 1.00 | 0.25 | 1 | 16 | 1304 | - |
| T03 | adr_constrained_feature | 1.00 | 0.21 | 1 | 19 | 1406 | - |
| T04 | schema | 1.00 | 0.29 | 1 | 14 | 1068 | - |
| T05 | superseded_trap | 1.00 | 0.14 | 1 | 22 | 1691 | - |
| T06 | assumption_trap | 1.00 | 0.19 | 1 | 21 | 1393 | - |
| T07 | vocabulary_mismatch | 1.00 | 0.31 | 2 | 13 | 915 | - |
| T08 | conventions | 1.00 | 0.11 | 1 | 19 | 1386 | - |
| T09 | missing_information | 1.00 | 0.12 | 1 | 8 | 675 | - |

Mean recall 1.00, mean precision 0.20, mean package ~1316 tokens = 0.50 of the full corpus.
Forbidden items returned: 0. Expected-unresolved misses: 0. Status mismatches: 0.

Recall by category: adr_constrained_feature 1.00, assumption_trap 1.00, bugfix 1.00, conventions 1.00, missing_information 1.00, schema 1.00, superseded_trap 1.00, vocabulary_mismatch 1.00
