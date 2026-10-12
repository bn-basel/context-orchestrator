# Own-loop experiment: trust (`20261012T023255Z-loop-trust`)

- Model `anthropic/claude-haiku-5.5` via OpenRouter (Anthropic provider pinned), commit `987b8e7ba9`
- Tokens are measured (API usage). Estimated cost uses list prices; measured cost is OpenRouter's reported charge (unavailable if any call's charge was not reported).
- Only arms of this loop are comparable with each other; 30 records.

| Arm | Runs | Failed | Mean score | Median input tokens | Median output | Est. cost | Measured cost | Median tool calls |
|---|---|---|---|---|---|---|---|---|
| T0 | 10 | 0 | 0.9667 | 89524.0 | 4351.0 | $0.0549 | $0.0549 | 15.0 |
| TR | 10 | 0 | 0.95 | 65089.0 | 3956.5 | $0.0498 | $0.0498 | 11.0 |
| TU | 10 | 0 | 0.95 | 98293.5 | 4281.0 | $0.0532 | $0.0532 | 12.5 |

| Comparison | Tasks | Input tokens (ratio) | Est. cost (ratio) | Measured cost (ratio) | Score difference |
|---|---|---|---|---|---|
| TR vs T0 | 5 | 0.8697 | 0.883 | 0.883 | -0.0167 |
| TU vs T0 | 5 | 1.0849 | 0.9476 | 0.9476 | -0.0167 |
| TR vs TU | 5 | 0.8017 | 0.9318 | 0.9318 | 0.0 |

| Task | Arm | Role | Score | Failed checks | Input tokens | Est. cost | Tool calls | Prunes | Error |
|---|---|---|---|---|---|---|---|---|---|
| F01 | T0 | task | 0.8333 | original_first | 47185 | 0.004749 | 9 | 0 | - |
| F01 | T0 | task | 0.8333 | original_first | 46162 | 0.004277 | 7 | 0 | - |
| F01 | TR | task | 0.6667 | original_first, tests | 38358 | 0.003786 | 8 | 0 | - |
| F01 | TR | task | 0.8333 | cause | 46275 | 0.004135 | 9 | 0 | - |
| F01 | TU | task | 0.8333 | tests | 19515 | 0.002631 | 4 | 0 | - |
| F01 | TU | task | 0.6667 | cause, original_first | 51495 | 0.003987 | 11 | 0 | - |
| F05 | T0 | task | 1.0 | - | 171963 | 0.007835 | 16 | 0 | - |
| F05 | T0 | task | 1.0 | - | 75149 | 0.005246 | 11 | 0 | - |
| F05 | TR | task | 1.0 | - | 120408 | 0.006609 | 17 | 0 | - |
| F05 | TR | task | 1.0 | - | 131190 | 0.006588 | 11 | 0 | - |
| F05 | TU | task | 1.0 | - | 68689 | 0.005353 | 11 | 0 | - |
| F05 | TU | task | 1.0 | - | 163720 | 0.006971 | 16 | 0 | - |
| F07 | T0 | task | 1.0 | - | 97345 | 0.005497 | 17 | 0 | - |
| F07 | T0 | task | 1.0 | - | 100350 | 0.005857 | 16 | 0 | - |
| F07 | TR | task | 1.0 | - | 157786 | 0.006948 | 18 | 0 | - |
| F07 | TR | task | 1.0 | - | 108034 | 0.006065 | 15 | 0 | - |
| F07 | TU | task | 1.0 | - | 169618 | 0.007193 | 22 | 0 | - |
| F07 | TU | task | 1.0 | - | 114853 | 0.00611 | 16 | 0 | - |
| F10 | T0 | task | 1.0 | - | 83042 | 0.005078 | 15 | 0 | - |
| F10 | T0 | task | 1.0 | - | 108757 | 0.005564 | 19 | 0 | - |
| F10 | TR | task | 1.0 | - | 67559 | 0.004769 | 13 | 0 | - |
| F10 | TR | task | 1.0 | - | 58408 | 0.003845 | 11 | 0 | - |
| F10 | TU | task | 1.0 | - | 166660 | 0.006524 | 20 | 0 | - |
| F10 | TU | task | 1.0 | - | 92596 | 0.00468 | 12 | 0 | - |
| F12 | T0 | task | 1.0 | - | 68149 | 0.005266 | 12 | 0 | - |
| F12 | T0 | task | 1.0 | - | 96006 | 0.005572 | 15 | 0 | - |
| F12 | TR | task | 1.0 | - | 62619 | 0.003553 | 10 | 0 | - |
| F12 | TR | task | 1.0 | - | 37601 | 0.00353 | 9 | 0 | - |
| F12 | TU | task | 1.0 | - | 103991 | 0.005596 | 13 | 0 | - |
| F12 | TU | task | 1.0 | - | 73307 | 0.004123 | 11 | 0 | - |
