# Agent comparison: hallpass (`20261011T053311Z-hallpass-agent`)

- Model `haiku`, 2.1.292 (Claude Code), commit `9150d83007`
- Tasks: H01, H06, H11, H13, H15; repetitions: 1
- Service config for B: `--retrieval hybrid --hops 2`
- Tokens and durations are measured (reported by Claude Code); cost is the CLI's API-list-price estimate, **not** a subscription charge.

| Strategy | Runs | Mean score | Successes | Traps hit | Median input tokens (uncached / cache read / cache write) | Median output | Median duration | API-equiv. cost (total) | Median tool calls (service) |
|---|---|---|---|---|---|---|---|---|---|
| B2: context service, told to use it first | 5 | 0.88 | 3 | 0 | 224279 (106 / 208345 / 15828) | 3546 | 56713 ms | $0.3946 | 12 (3) |
| B2C: as B2, compact packages (excerpts + locations) | 5 | 0.84 | 2 | 0 | 290514 (98 / 265650 / 21013) | 4069 | 51042 ms | $0.4164 | 18 (1) |

| Task | Strategy | Score | Failed checks | Traps | Input tokens | Tools |
|---|---|---|---|---|---|---|
| H01 | B2 | 0.8 | tests | - | 144187 | 7 |
| H01 | B2C | 0.8 | tests | - | 66780 | 5 |
| H06 | B2 | 1.0 | - | - | 224279 | 12 |
| H06 | B2C | 1.0 | - | - | 300030 | 22 |
| H11 | B2 | 1.0 | - | - | 354915 | 18 |
| H11 | B2C | 0.8 | migration_rules | - | 150313 | 14 |
| H13 | B2 | 0.6 | location, duplicate | - | 410467 | 16 |
| H13 | B2C | 0.6 | location, duplicate | - | 395904 | 19 |
| H15 | B2 | 1.0 | - | - | 120588 | 11 |
| H15 | B2C | 1.0 | - | - | 290514 | 18 |
