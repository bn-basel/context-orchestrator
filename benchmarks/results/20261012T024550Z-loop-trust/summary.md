# Own-loop experiment: trust (`20261012T024550Z-loop-trust`)

- Model `anthropic/claude-haiku-5.5` via OpenRouter (Anthropic provider pinned), commit `308b3a515b`
- Tokens are measured (API usage). Estimated cost uses list prices; measured cost is OpenRouter's reported charge (unavailable if any call's charge was not reported).
- Only arms of this loop are comparable with each other; 30 records.

| Arm | Runs | Failed | Mean score | Median input tokens | Median output | Est. cost | Measured cost | Median tool calls |
|---|---|---|---|---|---|---|---|---|
| T0 | 10 | 0 | 0.93 | 101405.0 | 4145.5 | $0.057 | $0.057 | 14.5 |
| TR | 10 | 0 | 0.8767 | 64807.0 | 4123.0 | $0.0433 | $0.0433 | 9.5 |
| TU | 10 | 0 | 0.95 | 86379.0 | 4414.5 | $0.0534 | $0.0534 | 14.5 |

| Comparison | Tasks | Input tokens (ratio) | Est. cost (ratio) | Measured cost (ratio) | Score difference |
|---|---|---|---|---|---|
| TR vs T0 | 5 | 0.6815 | 0.7624 | 0.7624 | -0.0533 |
| TU vs T0 | 5 | 0.8776 | 0.9363 | 0.9363 | 0.02 |
| TR vs TU | 5 | 0.7766 | 0.8142 | 0.8142 | -0.0733 |

| Task | Arm | Role | Score | Failed checks | Input tokens | Est. cost | Tool calls | Prunes | Error |
|---|---|---|---|---|---|---|---|---|---|
| F01 | T0 | task | 0.6667 | original_first, tests | 48638 | 0.003788 | 8 | 0 | - |
| F01 | T0 | task | 1.0 | - | 47932 | 0.00398 | 10 | 0 | - |
| F01 | TR | task | 0.8333 | original_first | 37894 | 0.003214 | 7 | 0 | - |
| F01 | TR | task | 0.6667 | original_first, tests | 29582 | 0.002856 | 4 | 0 | - |
| F01 | TU | task | 0.8333 | original_first | 40991 | 0.003593 | 9 | 0 | - |
| F01 | TU | task | 0.8333 | original_first | 44431 | 0.003596 | 6 | 0 | - |
| F05 | T0 | task | 0.8333 | toggle | 93674 | 0.006625 | 16 | 0 | - |
| F05 | T0 | task | 1.0 | - | 160223 | 0.008147 | 19 | 0 | - |
| F05 | TR | task | 0.8333 | toggle | 79107 | 0.005637 | 13 | 0 | - |
| F05 | TR | task | 0.8333 | toggle | 76495 | 0.004814 | 10 | 0 | - |
| F05 | TU | task | 1.0 | - | 96962 | 0.006179 | 15 | 0 | - |
| F05 | TU | task | 0.8333 | toggle | 86868 | 0.005847 | 17 | 0 | - |
| F07 | T0 | task | 0.8 | migration_off | 106050 | 0.006084 | 16 | 0 | - |
| F07 | T0 | task | 1.0 | - | 110150 | 0.00622 | 14 | 0 | - |
| F07 | TR | task | 0.8 | flags_table | 56070 | 0.004052 | 9 | 0 | - |
| F07 | TR | task | 0.8 | migration_off | 52078 | 0.003429 | 9 | 0 | - |
| F07 | TU | task | 1.0 | - | 134727 | 0.007043 | 17 | 0 | - |
| F07 | TU | task | 1.0 | - | 111652 | 0.006733 | 17 | 0 | - |
| F10 | T0 | task | 1.0 | - | 76368 | 0.004054 | 14 | 0 | - |
| F10 | T0 | task | 1.0 | - | 139929 | 0.005708 | 17 | 0 | - |
| F10 | TR | task | 1.0 | - | 150338 | 0.005413 | 18 | 0 | - |
| F10 | TR | task | 1.0 | - | 102878 | 0.004916 | 16 | 0 | - |
| F10 | TU | task | 1.0 | - | 140131 | 0.005612 | 17 | 0 | - |
| F10 | TU | task | 1.0 | - | 74648 | 0.005624 | 14 | 0 | - |
| F12 | T0 | task | 1.0 | - | 101898 | 0.006166 | 15 | 0 | - |
| F12 | T0 | task | 1.0 | - | 100912 | 0.006222 | 12 | 0 | - |
| F12 | TR | task | 1.0 | - | 73544 | 0.004922 | 15 | 0 | - |
| F12 | TR | task | 1.0 | - | 45347 | 0.004047 | 9 | 0 | - |
| F12 | TU | task | 1.0 | - | 85890 | 0.005025 | 14 | 0 | - |
| F12 | TU | task | 1.0 | - | 59773 | 0.004156 | 10 | 0 | - |
