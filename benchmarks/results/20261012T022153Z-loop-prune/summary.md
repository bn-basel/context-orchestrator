# Own-loop experiment: prune (`20261012T022153Z-loop-prune`)

- Model `anthropic/claude-haiku-5.5` via OpenRouter (Anthropic provider pinned), commit `da3ff4aca6`
- Tokens are measured (API usage). Estimated cost uses list prices; measured cost is OpenRouter's reported charge (unavailable if any call's charge was not reported).
- Only arms of this loop are comparable with each other; 30 records.

| Arm | Runs | Failed | Mean score | Median input tokens | Median output | Est. cost | Measured cost | Median tool calls |
|---|---|---|---|---|---|---|---|---|
| L | 10 | 0 | 0.92 | 89761.0 | 4340.5 | $0.0607 | $0.0607 | 16.0 |
| LC | 10 | 0 | 0.96 | 82765.5 | 3840.0 | $0.0562 | $0.0562 | 15.0 |
| LE | 10 | 0 | 0.96 | 59651.5 | 2646.0 | $0.0433 | $0.0433 | 12.0 |

| Comparison | Tasks | Input tokens (ratio) | Est. cost (ratio) | Measured cost (ratio) | Score difference |
|---|---|---|---|---|---|
| LC vs L | 5 | 0.9919 | 0.9124 | 0.9124 | 0.04 |
| LE vs L | 5 | 0.6744 | 0.7116 | 0.7116 | 0.04 |

| Task | Arm | Role | Score | Failed checks | Input tokens | Est. cost | Tool calls | Prunes | Error |
|---|---|---|---|---|---|---|---|---|---|
| H09 | L | task | 1.0 | - | 115040 | 0.007097 | 18 | 0 | - |
| H09 | L | task | 1.0 | - | 81576 | 0.006251 | 14 | 0 | - |
| H09 | LC | task | 1.0 | - | 98643 | 0.005657 | 15 | 0 | - |
| H09 | LC | task | 1.0 | - | 101038 | 0.005882 | 16 | 0 | - |
| H09 | LE | task | 1.0 | - | 65047 | 0.00445 | 12 | 0 | - |
| H09 | LE | task | 1.0 | - | 76746 | 0.005334 | 13 | 0 | - |
| H11 | L | task | 1.0 | - | 97321 | 0.004248 | 18 | 0 | - |
| H11 | L | task | 1.0 | - | 73256 | 0.005777 | 16 | 0 | - |
| H11 | LC | task | 1.0 | - | 86079 | 0.004696 | 16 | 0 | - |
| H11 | LC | task | 1.0 | - | 69239 | 0.005815 | 15 | 0 | - |
| H11 | LE | task | 1.0 | - | 37360 | 0.00327 | 10 | 0 | - |
| H11 | LE | task | 1.0 | - | 64240 | 0.004785 | 13 | 0 | - |
| H13 | L | task | 1.0 | - | 183297 | 0.008572 | 20 | 0 | - |
| H13 | L | task | 1.0 | - | 96473 | 0.00601 | 14 | 0 | - |
| H13 | LC | task | 1.0 | - | 253308 | 0.009422 | 25 | 0 | - |
| H13 | LC | task | 0.8 | decision | 169461 | 0.006625 | 21 | 0 | - |
| H13 | LE | task | 1.0 | - | 150605 | 0.006404 | 18 | 0 | - |
| H13 | LE | task | 1.0 | - | 69967 | 0.00454 | 15 | 0 | - |
| H17 | L | task | 1.0 | - | 77508 | 0.005651 | 12 | 0 | - |
| H17 | L | task | 1.0 | - | 54856 | 0.004841 | 9 | 0 | - |
| H17 | LC | task | 1.0 | - | 61736 | 0.004169 | 12 | 0 | - |
| H17 | LC | task | 1.0 | - | 61359 | 0.004086 | 11 | 0 | - |
| H17 | LE | task | 0.8 | finance | 52726 | 0.0042 | 9 | 0 | - |
| H17 | LE | task | 1.0 | - | 55063 | 0.003034 | 9 | 0 | - |
| H19 | L | task | 0.6 | not_built, meeting | 91643 | 0.006364 | 18 | 0 | - |
| H19 | L | task | 0.6 | not_found, not_built | 87879 | 0.00584 | 16 | 0 | - |
| H19 | LC | task | 1.0 | - | 79452 | 0.005324 | 14 | 0 | - |
| H19 | LC | task | 0.8 | not_built | 53156 | 0.004507 | 14 | 0 | - |
| H19 | LE | task | 1.0 | - | 38411 | 0.003494 | 9 | 0 | - |
| H19 | LE | task | 0.8 | not_found | 52374 | 0.003814 | 12 | 0 | - |
