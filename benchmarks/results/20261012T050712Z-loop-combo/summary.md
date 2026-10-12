# Own-loop experiment: combo (`20261012T050712Z-loop-combo`)

- Model `anthropic/claude-haiku-5.5` via OpenRouter (Anthropic provider pinned), commit `845215de68`
- Tokens are measured (API usage). Estimated cost uses list prices; measured cost is OpenRouter's reported charge (unavailable if any call's charge was not reported).
- Only arms of this loop are comparable with each other; 60 records.

| Arm | Runs | Failed | Mean score | Median input tokens | Median output | Est. cost | Measured cost | Median tool calls |
|---|---|---|---|---|---|---|---|---|
| L | 15 | 0 | 0.9533 | 154178 | 5109 | $0.1173 | $0.1173 | 17 |
| S | 15 | 0 | 0.9333 | 78050 | 4091 | $0.0722 | $0.0722 | 12 |
| SE | 15 | 0 | 0.9022 | 42498 | 2450 | $0.046 | $0.046 | 8 |
| TR | 15 | 0 | 0.9444 | 73741 | 3919 | $0.072 | $0.072 | 11 |

| Comparison | Tasks | Input tokens (ratio) | Est. cost (ratio) | Measured cost (ratio) | Score difference |
|---|---|---|---|---|---|
| S vs L | 5 | 0.4506 | 0.6125 | 0.6125 | -0.02 |
| SE vs L | 5 | 0.2586 | 0.3785 | 0.3785 | -0.0511 |
| SE vs S | 5 | 0.5738 | 0.6179 | 0.6179 | -0.0311 |
| TR vs L | 5 | 0.454 | 0.6024 | 0.6024 | -0.0089 |
| TR vs S | 5 | 1.0075 | 0.9834 | 0.9834 | 0.0111 |

| Task | Arm | Role | Score | Failed checks | Input tokens | Est. cost | Tool calls | Prunes | Error |
|---|---|---|---|---|---|---|---|---|---|
| F01 | L | task | 0.8333 | original_first | 75363 | 0.005392 | 12 | 0 | - |
| F01 | L | task | 0.8333 | original_first | 173246 | 0.008474 | 16 | 0 | - |
| F01 | L | task | 0.8333 | original_first | 132793 | 0.007089 | 14 | 0 | - |
| F01 | S | task | 0.6667 | original_first, tests | 19199 | 0.003475 | 6 | 0 | - |
| F01 | S | task | 1.0 | - | 25614 | 0.00361 | 6 | 0 | - |
| F01 | S | task | 0.6667 | cause, original_first | 38727 | 0.003608 | 5 | 0 | - |
| F01 | SE | task | 0.8333 | tests | 12157 | 0.001545 | 2 | 0 | - |
| F01 | SE | task | 1.0 | - | 21393 | 0.001606 | 4 | 0 | - |
| F01 | SE | task | 0.8333 | original_first | 17637 | 0.001857 | 5 | 0 | - |
| F01 | TR | task | 0.8333 | tests | 18849 | 0.002526 | 6 | 0 | - |
| F01 | TR | task | 0.6667 | original_first, tests | 24199 | 0.002979 | 7 | 0 | - |
| F01 | TR | task | 0.6667 | original_first, tests | 28152 | 0.003128 | 7 | 0 | - |
| F05 | L | task | 1.0 | - | 158006 | 0.009475 | 22 | 0 | - |
| F05 | L | task | 1.0 | - | 115273 | 0.00737 | 17 | 0 | - |
| F05 | L | task | 1.0 | - | 162067 | 0.00832 | 21 | 0 | - |
| F05 | S | task | 0.8333 | cancel_time | 114801 | 0.006284 | 17 | 0 | - |
| F05 | S | task | 1.0 | - | 89056 | 0.006135 | 16 | 0 | - |
| F05 | S | task | 0.8333 | toggle | 103264 | 0.00568 | 16 | 0 | - |
| F05 | SE | task | 1.0 | - | 63892 | 0.004987 | 11 | 0 | - |
| F05 | SE | task | 0.8333 | cache | 45121 | 0.003475 | 9 | 0 | - |
| F05 | SE | task | 0.8333 | toggle | 62273 | 0.004251 | 8 | 0 | - |
| F05 | TR | task | 1.0 | - | 79911 | 0.00502 | 17 | 0 | - |
| F05 | TR | task | 1.0 | - | 150747 | 0.007433 | 17 | 0 | - |
| F05 | TR | task | 1.0 | - | 73741 | 0.005642 | 11 | 0 | - |
| F07 | L | task | 1.0 | - | 154178 | 0.008276 | 21 | 0 | - |
| F07 | L | task | 0.8 | is_enabled | 283152 | 0.009535 | 25 | 0 | - |
| F07 | L | task | 1.0 | - | 293525 | 0.010904 | 22 | 0 | - |
| F07 | S | task | 1.0 | - | 78050 | 0.005103 | 10 | 0 | - |
| F07 | S | task | 1.0 | - | 99539 | 0.005397 | 14 | 0 | - |
| F07 | S | task | 1.0 | - | 66526 | 0.004285 | 11 | 0 | - |
| F07 | SE | task | 0.8 | is_enabled | 65101 | 0.003636 | 11 | 0 | - |
| F07 | SE | task | 0.6 | migration_off, is_enabled | 42498 | 0.003035 | 10 | 0 | - |
| F07 | SE | task | 1.0 | - | 78478 | 0.004107 | 10 | 0 | - |
| F07 | TR | task | 1.0 | - | 109386 | 0.005257 | 13 | 0 | - |
| F07 | TR | task | 1.0 | - | 72229 | 0.005127 | 11 | 0 | - |
| F07 | TR | task | 1.0 | - | 94921 | 0.00572 | 14 | 0 | - |
| F10 | L | task | 1.0 | - | 222223 | 0.009259 | 25 | 0 | - |
| F10 | L | task | 1.0 | - | 116136 | 0.007099 | 17 | 0 | - |
| F10 | L | task | 1.0 | - | 190651 | 0.007268 | 19 | 0 | - |
| F10 | S | task | 1.0 | - | 98007 | 0.004297 | 12 | 0 | - |
| F10 | S | task | 1.0 | - | 122627 | 0.005461 | 12 | 0 | - |
| F10 | S | task | 1.0 | - | 39875 | 0.003528 | 11 | 0 | - |
| F10 | SE | task | 1.0 | - | 20761 | 0.002196 | 6 | 0 | - |
| F10 | SE | task | 1.0 | - | 49209 | 0.003645 | 9 | 0 | - |
| F10 | SE | task | 1.0 | - | 57245 | 0.00328 | 8 | 0 | - |
| F10 | TR | task | 1.0 | - | 123571 | 0.00524 | 17 | 0 | - |
| F10 | TR | task | 1.0 | - | 52488 | 0.004043 | 8 | 0 | - |
| F10 | TR | task | 1.0 | - | 140104 | 0.005754 | 15 | 0 | - |
| F12 | L | task | 1.0 | - | 106173 | 0.005418 | 15 | 0 | - |
| F12 | L | task | 1.0 | - | 104895 | 0.00601 | 13 | 0 | - |
| F12 | L | task | 1.0 | - | 114304 | 0.007415 | 15 | 0 | - |
| F12 | S | task | 1.0 | - | 91629 | 0.005657 | 17 | 0 | - |
| F12 | S | task | 1.0 | - | 73975 | 0.005275 | 12 | 0 | - |
| F12 | S | task | 1.0 | - | 72227 | 0.00436 | 13 | 0 | - |
| F12 | SE | task | 1.0 | - | 42392 | 0.003396 | 8 | 0 | - |
| F12 | SE | task | 0.8 | hp489 | 39711 | 0.002435 | 7 | 0 | - |
| F12 | SE | task | 1.0 | - | 34220 | 0.002535 | 8 | 0 | - |
| F12 | TR | task | 1.0 | - | 53414 | 0.003713 | 9 | 0 | - |
| F12 | TR | task | 1.0 | - | 72761 | 0.005076 | 11 | 0 | - |
| F12 | TR | task | 1.0 | - | 86382 | 0.005348 | 15 | 0 | - |
