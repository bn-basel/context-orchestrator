# Agent comparison: hallpass (`20261011T054511Z-hallpass-agent`)

- Model `haiku`, 2.1.292 (Claude Code), commit `c9619faa27`
- Tasks: H01, H06, H11, H13, H15; repetitions: 1
- Service config for B: `--retrieval hybrid --hops 2`
- Tokens and durations are measured (reported by Claude Code); cost is the CLI's API-list-price estimate, **not** a subscription charge.

| Strategy | Runs | Mean score | Successes | Traps hit | Median input tokens (uncached / cache read / cache write) | Median output | Median duration | API-equiv. cost (total) | Median tool calls (service) |
|---|---|---|---|---|---|---|---|---|---|
| B2: context service, told to use it first | 5 | 0.92 | 3 | 0 | 223117 (106 / 206673 / 17718) | 3460 | 48646 ms | $0.3846 | 13 (1) |
| B2V: as B2, told to rely on the verbatim excerpts | 5 | 0.84 | 2 | 0 | 209780 (90 / 190901 / 15482) | 3613 | 51126 ms | $0.3691 | 14 (1) |

| Task | Strategy | Score | Failed checks | Traps | Input tokens | Tools |
|---|---|---|---|---|---|---|
| H01 | B2 | 0.8 | tests | - | 339996 | 16 |
| H01 | B2V | 0.8 | tests | - | 24013 | 1 |
| H06 | B2 | 1.0 | - | - | 198253 | 10 |
| H06 | B2V | 0.8 | channel | - | 199381 | 15 |
| H11 | B2 | 1.0 | - | - | 218533 | 13 |
| H11 | B2V | 0.6 | columns, unique | - | 265044 | 14 |
| H13 | B2 | 0.8 | decision | - | 223117 | 10 |
| H13 | B2V | 1.0 | - | - | 571213 | 24 |
| H15 | B2 | 1.0 | - | - | 286413 | 17 |
| H15 | B2V | 1.0 | - | - | 209780 | 10 |
