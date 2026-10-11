# Own-loop experiment: memory (`20261011T073027Z-loop-memory`)

- Model `anthropic/claude-haiku-5.5` via OpenRouter (Anthropic provider pinned), commit `2c42df0fef`
- Tokens are measured (API usage). Estimated cost uses list prices; measured cost is OpenRouter's reported charge (unavailable if any call's charge was not reported).
- Only arms of this loop are comparable with each other; 45 records.

| Arm | Runs | Failed | Mean score | Median input tokens | Median output | Est. cost | Measured cost | Median tool calls |
|---|---|---|---|---|---|---|---|---|
| SM | 15 | 0 | 0.9333 | 113779 | 4740 | $0.0941 | $0.0941 | 18 |
| SM0 | 15 | 0 | 0.94 | 112235 | 4736 | $0.0925 | $0.0925 | 17 |

| Comparison | Tasks | Input tokens (ratio) | Est. cost (ratio) | Measured cost (ratio) | Score difference |
|---|---|---|---|---|---|
| SM vs SM0 | 5 | 0.9292 | 1.0147 | 1.0147 | -0.0067 |

Parent (memory-building) runs: 15, ~$0.0869 estimated; findings recorded per run: [4, 4, 4, 4, 4, 4, 4, 5, 4, 5, 5, 5, 5, 4, 5]

| Task | Arm | Role | Score | Failed checks | Input tokens | Est. cost | Tool calls | Prunes | Error |
|---|---|---|---|---|---|---|---|---|---|
| F01 | SM | task | 0.8333 | original_first | 72882 | 0.005283 | 13 | 0 | - |
| F01 | SM | task | 0.8333 | original_first | 73469 | 0.005348 | 16 | 0 | - |
| F01 | SM | task | 0.6667 | original_first, tests | 74596 | 0.004918 | 17 | 0 | - |
| F01 | SM0 | task | 1.0 | - | 114311 | 0.006409 | 18 | 0 | - |
| F01 | SM0 | task | 0.8333 | original_first | 97906 | 0.005845 | 16 | 0 | - |
| F01 | SM0 | task | 0.8333 | original_first | 80236 | 0.005062 | 13 | 0 | - |
| F05 | SM | task | 1.0 | - | 116383 | 0.007096 | 16 | 0 | - |
| F05 | SM | task | 0.8333 | toggle | 168083 | 0.008232 | 21 | 0 | - |
| F05 | SM | task | 1.0 | - | 88811 | 0.005751 | 18 | 0 | - |
| F05 | SM0 | task | 0.8333 | toggle | 102103 | 0.005971 | 17 | 0 | - |
| F05 | SM0 | task | 1.0 | - | 103594 | 0.006 | 16 | 0 | - |
| F05 | SM0 | task | 1.0 | - | 93616 | 0.005649 | 16 | 0 | - |
| F07 | SM | task | 1.0 | - | 173169 | 0.007137 | 21 | 0 | - |
| F07 | SM | task | 1.0 | - | 120563 | 0.006323 | 19 | 0 | - |
| F07 | SM | task | 1.0 | - | 107941 | 0.006176 | 17 | 0 | - |
| F07 | SM0 | task | 1.0 | - | 190592 | 0.00758 | 21 | 0 | - |
| F07 | SM0 | task | 1.0 | - | 244756 | 0.007993 | 22 | 0 | - |
| F07 | SM0 | task | 0.8 | is_enabled | 117155 | 0.005477 | 17 | 0 | - |
| F10 | SM | task | 1.0 | - | 112658 | 0.005843 | 21 | 0 | - |
| F10 | SM | task | 0.8333 | tests | 142263 | 0.00637 | 19 | 0 | - |
| F10 | SM | task | 1.0 | - | 107849 | 0.005593 | 19 | 0 | - |
| F10 | SM0 | task | 1.0 | - | 126299 | 0.005311 | 20 | 0 | - |
| F10 | SM0 | task | 1.0 | - | 112235 | 0.005869 | 22 | 0 | - |
| F10 | SM0 | task | 1.0 | - | 265107 | 0.007918 | 22 | 0 | - |
| F12 | SM | task | 1.0 | - | 128248 | 0.005636 | 18 | 0 | - |
| F12 | SM | task | 1.0 | - | 113779 | 0.006104 | 18 | 0 | - |
| F12 | SM | task | 1.0 | - | 174919 | 0.008312 | 24 | 0 | - |
| F12 | SM0 | task | 0.8 | hp489 | 136515 | 0.006951 | 19 | 0 | - |
| F12 | SM0 | task | 1.0 | - | 85143 | 0.00541 | 14 | 0 | - |
| F12 | SM0 | task | 1.0 | - | 75381 | 0.005053 | 15 | 0 | - |
| H01 | SM | parent | 1.0 | - | 75314 | 0.005255 | 17 | 0 | - |
| H01 | SM | parent | 0.8 | cause | 120636 | 0.006384 | 16 | 0 | - |
| H01 | SM | parent | 1.0 | - | 61093 | 0.004649 | 13 | 0 | - |
| H05 | SM | parent | 1.0 | - | 76655 | 0.004565 | 13 | 0 | - |
| H05 | SM | parent | 1.0 | - | 75815 | 0.003902 | 13 | 0 | - |
| H05 | SM | parent | 1.0 | - | 97032 | 0.004461 | 14 | 0 | - |
| H07 | SM | parent | 1.0 | - | 152607 | 0.005902 | 18 | 0 | - |
| H07 | SM | parent | 1.0 | - | 294024 | 0.008772 | 23 | 0 | - |
| H07 | SM | parent | 1.0 | - | 301756 | 0.009345 | 24 | 0 | - |
| H10 | SM | parent | 1.0 | - | 30503 | 0.002926 | 10 | 0 | - |
| H10 | SM | parent | 1.0 | - | 61707 | 0.003936 | 11 | 0 | - |
| H10 | SM | parent | 1.0 | - | 38984 | 0.00306 | 13 | 0 | - |
| H12 | SM | parent | 0.8 | yesterday | 193882 | 0.00698 | 18 | 0 | - |
| H12 | SM | parent | 0.8 | yesterday | 192741 | 0.008002 | 21 | 0 | - |
| H12 | SM | parent | 1.0 | - | 193760 | 0.008797 | 25 | 0 | - |
