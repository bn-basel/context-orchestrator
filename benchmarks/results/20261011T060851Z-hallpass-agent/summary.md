# Agent comparison: hallpass (`20261011T060851Z-hallpass-agent`)

- Model `haiku`, 2.1.292 (Claude Code), commit `b67570b4e2`
- Tasks: H01, H06, H11, H13, H15; repetitions: 2
- Service config for B: `--retrieval hybrid --hops 2`
- Tokens and durations are measured (reported by Claude Code); cost is the CLI's API-list-price estimate, **not** a subscription charge.

| Strategy | Runs | Mean score | Successes | Traps hit | Median input tokens (uncached / cache read / cache write) | Median output | Median duration | API-equiv. cost (total) | Median tool calls (service) |
|---|---|---|---|---|---|---|---|---|---|
| E: reader sub-agent does all file reading | 10 | 0.78 | 3 | 0 | 351180.0 (5852.0 / 285090.5 / 39269.0) | 7700.0 | 90797.5 ms | $1.3702 | 30.5 (0.0) |

| Task | Strategy | Score | Failed checks | Traps | Input tokens | Tools |
|---|---|---|---|---|---|---|
| H01 | E | 0.8 | tests | - | 177216 | 23 |
| H01 | E | 1.0 | - | - | 243435 | 28 |
| H06 | E | 0.8 | channel | - | 279246 | 29 |
| H06 | E | 1.0 | - | - | 345975 | 34 |
| H11 | E | 0.4 | columns, unique, availability | - | 543402 | 38 |
| H11 | E | 0.6 | columns, migration_rules | - | 423170 | 27 |
| H13 | E | 0.8 | decision | - | 417704 | 53 |
| H13 | E | 0.6 | duplicate, decision | - | 364495 | 32 |
| H15 | E | 1.0 | - | - | 356385 | 33 |
| H15 | E | 0.8 | adr | - | 80728 | 17 |
