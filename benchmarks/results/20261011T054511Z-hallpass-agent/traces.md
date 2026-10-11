# What agents read

Reads classified against what the service had already returned in the run and the task's labelled ranges. 'Carried' = result size x later tool calls (it is re-sent with each), a proxy for its input-token cost.

| Strategy | Reads/run | Read chars/run | Reads: served / needed-missed / same file / unrelated | Share of carried context: Read / Grep / Glob / service |
|---|---|---|---|---|
| B2 | 5.4 | 20,967 | 7 / 8 / 0 / 12 | 44% / 2% / 6% / 48% |
| B2V | 4.4 | 17,069 | 5 / 5 / 0 / 12 | 38% / 4% / 1% / 56% |

| Strategy | Labelled ranges: served by service / read by the agent only / never seen | Mean score when 0 / 1 / 2+ labelled ranges were never seen (runs) |
|---|---|---|
| B2 | 32% / 32% / 36% | None (0) / 0.9 (2) / 0.933 (3) |
| B2V | 36% / 21% / 43% | None (0) / None (0) / 0.84 (5) |
