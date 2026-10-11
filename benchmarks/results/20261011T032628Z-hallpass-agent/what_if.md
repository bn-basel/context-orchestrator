# What-if estimates (replayed recordings, no model calls)

Cost model per strategy: input tokens ≈ a per model call + b per carried character.

| Strategy | Runs | a (tokens per call) | b (tokens per carried char) | Correlation, log predicted vs log actual |
|---|---|---|---|---|
| A | 60 | 121,494 | -0.332 | 0.92 |
| B | 60 | 1,445 | 0.468 | 0.92 |
| B2 | 60 | 2,525 | 0.545 | 0.93 |
| C | 60 | 3,235 | 0.393 | 0.85 |
| D | 60 | 7,782 | 0.225 | 0.96 |

Change in input tokens per run, mean (median), **assuming the agent behaves the same otherwise** (an upper bound on savings). n/a: policy does not apply; -: no usable cost fit for that strategy.

| Policy | A | B | B2 | C | D |
|---|---|---|---|---|---|
| complete_first_answer | - | -4% (+0%) | -5% (+0%) | n/a | n/a |
| prune_after_10 | - | -19% (-18%) | -13% (-8%) | -16% (-13%) | -3% (-0%) |
| prune_after_3 | - | -59% (-62%) | -48% (-52%) | -53% (-53%) | -15% (-14%) |
| prune_after_5 | - | -45% (-48%) | -33% (-37%) | -40% (-40%) | -10% (-7%) |
| targeted_reads_2k | - | -1% (+0%) | -8% (-3%) | n/a | n/a |
| whole_files_16k | - | +24% (+13%) | +59% (+53%) | n/a | n/a |
| whole_files_32k | - | +24% (+13%) | +59% (+53%) | n/a | n/a |
| whole_files_4k | - | +7% (+2%) | +20% (+18%) | n/a | n/a |
| whole_files_8k | - | +18% (+7%) | +45% (+39%) | n/a | n/a |
