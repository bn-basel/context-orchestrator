# Paired analysis

300 successful runs over 20 tasks. Differences are per-task paired; 95% intervals from a bootstrap over tasks (10000 samples, seed 20261011). An interval containing 0 (or 1.00 for ratios) means no detectable difference.

| Comparison | Score difference [95% CI] | Success-rate difference [95% CI] | Input-token ratio [95% CI] | Cost ratio [95% CI] |
|---|---|---|---|---|
| A vs C | +0.035 [-0.015, +0.080] | +0.133 [+0.000, +0.267] | 5.12x [4.00, 6.35] | 1.97x [1.59, 2.32] |
| B vs C | -0.008 [-0.081, +0.060] | +0.050 [-0.100, +0.217] | 0.90x [0.70, 1.12] | 0.93x [0.81, 1.05] |
| B2 vs C | -0.017 [-0.060, +0.026] | +0.017 [-0.117, +0.150] | 0.78x [0.61, 0.97] | 0.79x [0.69, 0.89] |
| D vs C | +0.048 [-0.012, +0.111] | +0.150 [+0.000, +0.317] | 0.39x [0.28, 0.52] | 0.57x [0.47, 0.67] |
| B vs A | -0.043 [-0.115, +0.022] | -0.083 [-0.267, +0.100] | 0.18x [0.13, 0.23] | 0.47x [0.38, 0.60] |
| B2 vs A | -0.052 [-0.094, -0.009] | -0.117 [-0.283, +0.033] | 0.15x [0.12, 0.20] | 0.40x [0.33, 0.50] |
| C vs A | -0.035 [-0.080, +0.015] | -0.133 [-0.267, -0.000] | 0.20x [0.16, 0.25] | 0.51x [0.43, 0.63] |
| D vs A | +0.013 [-0.052, +0.075] | +0.017 [-0.150, +0.183] | 0.08x [0.05, 0.12] | 0.29x [0.22, 0.39] |

| Strategy | Runs | Runs using the service | Mean service calls | Median file-tool calls |
|---|---|---|---|---|
| A | 60 | 0 | 0.00 | 13.0 |
| B | 60 | 42 | 1.08 | 16.5 |
| B2 | 60 | 59 | 1.87 | 12.0 |
| C | 60 | 0 | 0.00 | 17.0 |
| D | 60 | 0 | 0.00 | 11.0 |
