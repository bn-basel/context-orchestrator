# Own-loop experiment: prune (`20261011T071428Z-loop-prune`)

- Model `anthropic/claude-haiku-5.5` via OpenRouter (Anthropic provider pinned), commit `5ac953ee21`
- Tokens are measured (API usage). Estimated cost uses list prices; measured cost is OpenRouter's reported charge (unavailable if any call's charge was not reported).
- Only arms of this loop are comparable with each other; 10 records.

| Arm | Runs | Failed | Mean score | Median input tokens | Median output | Est. cost | Measured cost | Median tool calls |
|---|---|---|---|---|---|---|---|---|
| L | 5 | 0 | 0.92 | 93146 | 3623 | $0.0311 | $0.0311 | 16 |
| LP | 5 | 0 | 0.96 | 76497 | 4830 | $0.0359 | $0.0359 | 21 |

| Comparison | Tasks | Input tokens (ratio) | Est. cost (ratio) | Measured cost (ratio) | Score difference |
|---|---|---|---|---|---|
| LP vs L | 5 | 0.9461 | 1.1679 | 1.1679 | 0.04 |

| Task | Arm | Role | Score | Failed checks | Input tokens | Est. cost | Tool calls | Prunes | Error |
|---|---|---|---|---|---|---|---|---|---|
| H09 | L | task | 1.0 | - | 90088 | 0.007481 | 16 | 0 | - |
| H09 | LP | task | 1.0 | - | 76497 | 0.006833 | 20 | 1 | - |
| H11 | L | task | 1.0 | - | 93146 | 0.005439 | 16 | 0 | - |
| H11 | LP | task | 1.0 | - | 109081 | 0.008297 | 28 | 1 | - |
| H13 | L | task | 1.0 | - | 149217 | 0.007339 | 18 | 0 | - |
| H13 | LP | task | 1.0 | - | 72811 | 0.006642 | 21 | 1 | - |
| H17 | L | task | 0.8 | finance | 52534 | 0.004612 | 10 | 0 | - |
| H17 | LP | task | 1.0 | - | 73952 | 0.006392 | 19 | 1 | - |
| H19 | L | task | 0.8 | not_found | 99094 | 0.006184 | 18 | 0 | - |
| H19 | LP | task | 0.8 | not_built | 109996 | 0.007688 | 22 | 1 | - |
