# Agent comparison: hallpass (`20261011T030237Z-hallpass-agent`)

- Model `haiku`, 2.1.292 (Claude Code), commit `0c77c9015a`
- Tasks: H01, H12, H15, H17; repetitions: 1
- Service config for B: `--retrieval hybrid --hops 2`
- Tokens and durations are measured (reported by Claude Code); cost is the CLI's API-list-price estimate, **not** a subscription charge.

| Strategy | Runs | Mean score | Successes | Traps hit | Median input tokens (uncached / cache read / cache write) | Median output | Median duration | API-equiv. cost (total) | Median tool calls (service) |
|---|---|---|---|---|---|---|---|---|---|
| A: full context | 4 | 0.8 | 1 | 1 | 1605049.5 (70.0 / 1500517.5 / 16062.0) | 3415.5 | 54849.5 ms | $1.1046 | 12.0 (0.0) |
| B: context service (MCP tool) | 4 | 0.9 | 2 | 0 | 236007.5 (86.0 / 207000.0 / 28921.5) | 4813.0 | 58480.5 ms | $0.4454 | 16.0 (0.5) |
| C: no context (file tools only) | 4 | 0.7 | 1 | 0 | 366196.5 (138.0 / 337808.5 / 29426.0) | 4545.5 | 76903.0 ms | $0.4889 | 20.5 (0.0) |
| D: oracle (labelled ranges only) | 4 | 0.75 | 1 | 0 | 164230.0 (74.0 / 148613.5 / 15542.5) | 3665.5 | 47248.5 ms | $0.3119 | 11.5 (0.0) |

| Task | Strategy | Score | Failed checks | Traps | Input tokens | Tools |
|---|---|---|---|---|---|---|
| H01 | A | 0.8 | tests | - | 1126581 | 9 |
| H01 | B | 1.0 | - | - | 210665 | 16 |
| H01 | C | 0.8 | tests | - | 403870 | 18 |
| H01 | D | 1.0 | - | - | 122918 | 10 |
| H12 | A | 0.8 | call | - | 552392 | 5 |
| H12 | B | 0.8 | yesterday | - | 178264 | 16 |
| H12 | C | 0.6 | yesterday, manual | - | 249536 | 16 |
| H12 | D | 0.4 | call, yesterday, manual | - | 59196 | 5 |
| H15 | A | 1.0 | - | - | 2083518 | 15 |
| H15 | B | 1.0 | - | - | 261350 | 15 |
| H15 | C | 1.0 | - | - | 328523 | 23 |
| H15 | D | 0.8 | full_tier | - | 205542 | 13 |
| H17 | A | 0.6 | render, finance | fact | 2096201 | 17 |
| H17 | B | 0.8 | finance | - | 577541 | 38 |
| H17 | C | 0.4 | unconfirmed, ref, finance | - | 686975 | 39 |
| H17 | D | 0.8 | finance | - | 618480 | 25 |
