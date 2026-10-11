# Own-loop experiment: memory (`20261011T072205Z-loop-memory`)

- Model `anthropic/claude-haiku-5.5` via OpenRouter (Anthropic provider pinned), commit `3b0d692541`
- Tokens are measured (API usage). Estimated cost uses list prices; measured cost is OpenRouter's reported charge (unavailable if any call's charge was not reported).
- Only arms of this loop are comparable with each other; 15 records.

| Arm | Runs | Failed | Mean score | Median input tokens | Median output | Est. cost | Measured cost | Median tool calls |
|---|---|---|---|---|---|---|---|---|
| SM | 5 | 0 | 0.9333 | 124837 | 4768 | $0.031 | $0.031 | 17 |
| SM0 | 5 | 0 | 0.9667 | 144299 | 5358 | $0.0361 | $0.0361 | 19 |

| Comparison | Tasks | Input tokens (ratio) | Est. cost (ratio) | Measured cost (ratio) | Score difference |
|---|---|---|---|---|---|
| SM vs SM0 | 5 | 0.7984 | 0.891 | 0.891 | -0.0333 |

Parent (memory-building) runs: 5, ~$0.0256 estimated; findings recorded per run: [4, 4, 4, 4, 4]

| Task | Arm | Role | Score | Failed checks | Input tokens | Est. cost | Tool calls | Prunes | Error |
|---|---|---|---|---|---|---|---|---|---|
| F01 | SM | task | 0.8333 | original_first | 79256 | 0.005657 | 15 | 0 | - |
| F01 | SM0 | task | 1.0 | - | 53864 | 0.004448 | 13 | 0 | - |
| F05 | SM | task | 0.8333 | toggle | 105846 | 0.006521 | 19 | 0 | - |
| F05 | SM0 | task | 0.8333 | toggle | 161486 | 0.007666 | 19 | 0 | - |
| F07 | SM | task | 1.0 | - | 157334 | 0.007084 | 20 | 0 | - |
| F07 | SM0 | task | 1.0 | - | 428831 | 0.010678 | 27 | 0 | - |
| F10 | SM | task | 1.0 | - | 124837 | 0.005876 | 17 | 0 | - |
| F10 | SM0 | task | 1.0 | - | 144299 | 0.006379 | 25 | 0 | - |
| F12 | SM | task | 1.0 | - | 136327 | 0.005897 | 16 | 0 | - |
| F12 | SM0 | task | 1.0 | - | 128644 | 0.006942 | 19 | 0 | - |
| H01 | SM | parent | 1.0 | - | 56966 | 0.004395 | 11 | 0 | - |
| H05 | SM | parent | 0.75 | tests | 36791 | 0.003447 | 11 | 0 | - |
| H07 | SM | parent | 1.0 | - | 130669 | 0.005872 | 19 | 0 | - |
| H10 | SM | parent | 1.0 | - | 131895 | 0.005019 | 16 | 0 | - |
| H12 | SM | parent | 0.8 | yesterday | 136934 | 0.006882 | 16 | 0 | - |
