# Own-loop experiment: combo (`20261012T034938Z-loop-combo`)

- Model `anthropic/claude-haiku-5.5` via OpenRouter (Anthropic provider pinned), commit `d8a1c2a134`
- Tokens are measured (API usage). Estimated cost uses list prices; measured cost is OpenRouter's reported charge (unavailable if any call's charge was not reported).
- Only arms of this loop are comparable with each other; 45 records.

| Arm | Runs | Failed | Mean score | Median input tokens | Median output | Est. cost | Measured cost | Median tool calls |
|---|---|---|---|---|---|---|---|---|
| L | 15 | 0 | 0.9444 | 127730 | 4631 | $0.1076 | $0.1076 | 16 |
| S | 15 | 0 | 0.92 | 71543 | 3910 | $0.0733 | $0.0733 | 12 |
| X | 15 | 0 | 0.7956 | 22542 | 1837 | $0.0311 | $0.0311 | 4 |

| Comparison | Tasks | Input tokens (ratio) | Est. cost (ratio) | Measured cost (ratio) | Score difference |
|---|---|---|---|---|---|
| S vs L | 5 | 0.6098 | 0.6791 | 0.6791 | -0.0245 |
| X vs L | 5 | 0.1821 | 0.2847 | 0.2847 | -0.1489 |
| X vs S | 5 | 0.2987 | 0.4192 | 0.4192 | -0.1244 |

| Task | Arm | Role | Score | Failed checks | Input tokens | Est. cost | Tool calls | Prunes | Error |
|---|---|---|---|---|---|---|---|---|---|
| F01 | L | task | 0.5 | cause, original_first, tests | 106671 | 0.006075 | 13 | 0 | - |
| F01 | L | task | 1.0 | - | 113246 | 0.007205 | 14 | 0 | - |
| F01 | L | task | 0.6667 | original_first, tests | 90370 | 0.006565 | 14 | 0 | - |
| F01 | S | task | 0.8333 | original_first | 39992 | 0.003867 | 9 | 0 | - |
| F01 | S | task | 0.8333 | original_first | 43099 | 0.004034 | 11 | 0 | - |
| F01 | S | task | 0.6667 | cause, original_first | 59464 | 0.003823 | 10 | 0 | - |
| F01 | X | task | 0.8333 | original_first | 14993 | 0.001822 | 2 | 0 | - |
| F01 | X | task | 0.6667 | original_first, tests | 23000 | 0.002095 | 5 | 0 | - |
| F01 | X | task | 0.8333 | cause | 5929 | 0.001144 | 1 | 0 | - |
| F05 | L | task | 1.0 | - | 153538 | 0.00832 | 20 | 0 | - |
| F05 | L | task | 1.0 | - | 129942 | 0.008351 | 21 | 0 | - |
| F05 | L | task | 1.0 | - | 164571 | 0.00966 | 20 | 0 | - |
| F05 | S | task | 0.8333 | toggle | 29796 | 0.002701 | 5 | 0 | - |
| F05 | S | task | 1.0 | - | 146855 | 0.007162 | 17 | 0 | - |
| F05 | S | task | 1.0 | - | 106551 | 0.006564 | 16 | 0 | - |
| F05 | X | task | 0.6667 | cache, toggle | 11953 | 0.001414 | 2 | 0 | - |
| F05 | X | task | 0.6667 | cache, toggle | 17411 | 0.00181 | 3 | 0 | - |
| F05 | X | task | 0.6667 | cache, toggle | 16310 | 0.001554 | 3 | 0 | - |
| F07 | L | task | 1.0 | - | 128542 | 0.006579 | 16 | 0 | - |
| F07 | L | task | 1.0 | - | 148489 | 0.008139 | 20 | 0 | - |
| F07 | L | task | 1.0 | - | 107905 | 0.006882 | 18 | 0 | - |
| F07 | S | task | 1.0 | - | 98853 | 0.005581 | 16 | 0 | - |
| F07 | S | task | 0.8 | migration_off | 101182 | 0.00619 | 16 | 0 | - |
| F07 | S | task | 1.0 | - | 71543 | 0.004433 | 12 | 0 | - |
| F07 | X | task | 0.6 | checkout, toggle | 18763 | 0.00195 | 3 | 0 | - |
| F07 | X | task | 0.6 | migration_off, toggle | 33298 | 0.002715 | 6 | 0 | - |
| F07 | X | task | 0.6 | migration_off, toggle | 9907 | 0.001156 | 2 | 0 | - |
| F10 | L | task | 1.0 | - | 127730 | 0.006381 | 17 | 0 | - |
| F10 | L | task | 1.0 | - | 151537 | 0.006539 | 15 | 0 | - |
| F10 | L | task | 1.0 | - | 113320 | 0.006782 | 16 | 0 | - |
| F10 | S | task | 1.0 | - | 82177 | 0.005217 | 15 | 0 | - |
| F10 | S | task | 0.8333 | tests | 66847 | 0.003362 | 10 | 0 | - |
| F10 | S | task | 1.0 | - | 53852 | 0.00426 | 12 | 0 | - |
| F10 | X | task | 1.0 | - | 22542 | 0.002133 | 5 | 0 | - |
| F10 | X | task | 1.0 | - | 37072 | 0.00297 | 4 | 0 | - |
| F10 | X | task | 1.0 | - | 26638 | 0.001993 | 5 | 0 | - |
| F12 | L | task | 1.0 | - | 105675 | 0.006421 | 15 | 0 | - |
| F12 | L | task | 1.0 | - | 148416 | 0.007192 | 18 | 0 | - |
| F12 | L | task | 1.0 | - | 100441 | 0.00648 | 14 | 0 | - |
| F12 | S | task | 1.0 | - | 65443 | 0.004252 | 11 | 0 | - |
| F12 | S | task | 1.0 | - | 117657 | 0.006061 | 14 | 0 | - |
| F12 | S | task | 1.0 | - | 99160 | 0.005798 | 15 | 0 | - |
| F12 | X | task | 1.0 | - | 59929 | 0.003445 | 11 | 0 | - |
| F12 | X | task | 1.0 | - | 51336 | 0.002632 | 8 | 0 | - |
| F12 | X | task | 0.8 | hp489 | 27876 | 0.002285 | 5 | 0 | - |
