# What agents read

Reads classified against what the service had already returned in the run and the task's labelled ranges. 'Carried' = result size x later tool calls (it is re-sent with each), a proxy for its input-token cost.

| Strategy | Reads/run | Read chars/run | Reads: served / needed-missed / same file / unrelated | Share of carried context: Read / Grep / Glob / service |
|---|---|---|---|---|
| A | 5.93 | 21,665 | 0 / 180 / 0 / 176 | 90% / 8% / 1% / 0% |
| B | 8.85 | 36,231 | 36 / 171 / 3 / 321 | 68% / 5% / 12% / 15% |
| B2 | 5.4 | 22,558 | 79 / 74 / 8 / 163 | 50% / 4% / 7% / 39% |
| C | 10.47 | 44,584 | 0 / 216 / 0 / 412 | 83% / 4% / 12% / 0% |
| D | 6.38 | 25,449 | 0 / 167 / 0 / 216 | 86% / 4% / 9% / 0% |

| Strategy | Labelled ranges: served by service / read by the agent only / never seen | Mean score when 0 / 1 / 2+ labelled ranges were never seen (runs) |
|---|---|---|
| A | n/a (context given in the prompt) | n/a |
| B | 18% / 55% / 27% | 0.909 (11) / 0.835 (23) / 0.719 (26) |
| B2 | 33% / 30% / 37% | 0.9 (4) / 0.8 (16) / 0.775 (40) |
| C | 0% / 72% / 28% | 0.825 (10) / 0.846 (24) / 0.763 (26) |
| D | n/a (context given in the prompt) | n/a |
