# Roadmap

The project moves in phases separated by decision gates. A phase that adds
features starts only when the previous gate's evidence supports it, and a
negative result is written up rather than worked around.

```
Phase 0  foundation ─▶ Phase 1  measure retrieval ─▶ Phase 1b  larger corpus ─▶ Phase 1c  improve retrieval
   ─▶ Gate 1 (single request: not passed) ─▶ Phase 2  agent comparison ─▶ Gate 2 (answered for one setting)
   ─▶ Phase 3  why savings stop where they do ─▶ Next: in-place pruning, multi-task memory, robustness
```

## Phase 0: foundation (done)

- [x] Ingest Markdown, Python, SQL and config files into SQLite, incrementally
      by file hash. One state directory; project files are never written.
- [x] Structure-aware chunking with exact line ranges and file hashes.
- [x] Front matter `kind` / `status`; kind inference from paths.
- [x] BM25 keyword retrieval (FTS5, Porter stemming) with matched-term
      explanations and per-kind filtering.
- [x] Context packages: round-robin token budget, superseded items omitted
      with a reason, assumptions flagged, stale sources detected, unresolved
      kinds reported.
- [x] Python API (`ContextService`) and CLI (`ctxo ingest`, `ctxo request`).
- [x] JSONL telemetry; task text excluded by default; every metric labelled
      measured, estimated or unavailable.
- [x] Parser for `claude -p --output-format json` usage.

## Phase 1: measure retrieval without a model (done)

- [x] Nine labelled tasks on the sample project, covering bug fixes,
      ADR-constrained work, schema, superseded and assumption traps,
      vocabulary mismatch, conventions and missing information.
- [x] Gate 1 criteria fixed and committed before the first run.
- [x] `ctxo eval-retrieval`: recall, precision, first relevant rank,
      forbidden items, expected-unresolved kinds, status mismatches, package
      size vs. corpus. Raw results stored per run.
- [x] First run: **gate 1 passed narrowly** (recall 0.83, precision 0.40).
      Findings and caveats: [benchmarks/README.md](benchmarks/README.md).

## Phase 1b: a corpus where the question matters (done)

- [x] Hallpass: synthetic corpus by four separate authoring agents, ~140k
      tokens (estimated), 54× the sample. Spec kept outside the corpus.
- [x] 20 tasks / 107 labels by a fifth agent that saw only the corpus,
      committed before the first run.
- [x] Gate 1 re-run: **not passed** (recall 0.56, two missed "not found"
      cases). Diagnostic sweep shows ranking is the main loss, reach (~15%)
      the smaller one. Details: [benchmarks/README.md](benchmarks/README.md).

## Phase 1c: improve retrieval (done)

Development set: the 20 Hallpass tasks. Log: [benchmarks/README.md](benchmarks/README.md).

- [x] Budget covers the rendered package (bug fix, kept).
- [x] Weak-match filter `min_relative_score` (precision dial, not a
      missing-information detector; off).
- [x] Standard NLTK stopwords (kept).
- [x] Reference following `max_references` (finds named functions but is
      zero-sum at a fixed budget; off).
- [x] Hybrid retrieval with local embeddings (`--retrieval hybrid`): fixes
      vocabulary mismatch (sample 0.81 → 0.94), barely moves Hallpass.
- [x] Two-step retrieval `--hops 2`: query drift with BM25 seeds; with hybrid
      seeds the best result so far (Hallpass recall 0.61, precision 0.32).
- [x] Conclusion: **no single-request method reaches gate 1 (0.80)** on
      realistic tasks; the missing pieces need reasoning-driven hops.

## Gate 1 (single request per task): not passed

Originally to be judged on a held-out set after phase 1c. Since no method
passes on the development set, the held-out set is only needed to confirm a
configuration choice. The criteria in
[benchmarks/gate1.json](benchmarks/gate1.json) stay as committed: changing them
after seeing results would be moving the goalposts.

## Phase 2: agent comparison (done)

- [x] MCP server (`ctxo mcp`) and runner (`ctxo eval-agent`) for strategies
      A–D via `claude -p`, with isolation flags, stream parsing, usage,
      regex rubric grading and sanitised raw output.
- [x] Pilot: 4 tasks × 4 strategies × 1 run on Haiku (results in
      benchmarks/README.md). Strategy B used the tool in only 2 of 4 runs.
- [x] Full run: 20 tasks × 5 strategies (A, B, B2, C, D) × 3 on Haiku,
      paired bootstrap analysis (`ctxo analyze-agent`). Results in
      benchmarks/README.md.

- [ ] Benchmark runner for strategies A (full context) and B (on-demand
      retrieval), then C (no context) and D (oracle), via `claude -p` with the
      isolation flags in the methodology. Raw results as JSONL.
- [ ] Verify what user-level context loads under those flags on a subscription.
- [ ] Hidden test suites per task for objective success.
- [ ] Versioned price table with source and date, kept separate from the
      CLI's `costUSD`.
- [ ] Analysis from raw files only: per-task medians and spreads.

## Gate 2: answered for one setting

Does on-demand retrieval use fewer tokens at the same task success? On the
Hallpass corpus with Haiku 4.5: **yes against unaided exploration when the
agent is told to use the service** (0.78× input tokens, 0.79× cost, no
detectable quality difference); **no when the tool is merely offered**
(savings within noise). Against full context it uses ~0.15× the tokens and
~0.40× the cost, at a small quality cost (−0.05). Written up in
[benchmarks/README.md](benchmarks/README.md). Generality (other corpora,
models, graders) is untested.

## Phase 3: why the savings stop where they do (done)

- [x] MCP server exposing `request_context` (`ctxo mcp`).
- [x] 3a: compact excerpts raise retrieval recall (0.61 → 0.74) but show no
      agent benefit in a 10-run check (the agent opens the files instead).
- [x] 3b: trace analysis of the 300 runs (`ctxo analyze-traces`): with the
      service, agents read half as much, but 35% of what they still read was
      already served; "rely on the excerpts" instructions didn't change that.
- [x] 3c: what-if replay (`ctxo what-if`): whole-file answers would cost more;
      **pruning old tool output in place could save 33–53% of input tokens**
      (upper bound, untested).
- [x] 3d: a reader sub-agent doing all reading is worse (1.27× tokens, lower
      quality).
- [x] Hybrid retrieval (BM25 + local embeddings) and follow-up hops, added
      once keyword search had demonstrably stalled.

## Phase 4: pruning and memory in our own loop (done)

- [x] Own agent loop with client-side pruning, measured usage and spending
      brakes (`ctxo loop-probe`, `ctxo loop-eval`).
- [x] Memory write path: anchored, unreviewed findings (`record_finding`),
      served before search results, flagged stale when the file changes.
- [x] Five follow-up tasks with rubrics, committed before any run. Offline
      ceiling: one request's recall 0.24 → 0.45 with ideal parent memory.
- [x] 4a: pruning check, 10 runs on Haiku 5.5 ($0.07): tokens ×0.95, cost ×1.17,
      no saving. The model works in few, wide steps, and pruned agents re-read.
- [x] 4b: memory check, 15 runs on Haiku 5.5 ($0.09): findings accurate and
      served; follow-ups ×0.80 tokens, ×0.89 cost (4 of 5 cheaper, mostly one
      task), score −0.03. Replication (45 runs, $0.27): cost ×1.02 [0.92–1.14];
      pooled ×0.98. No saving: agents opened 30 of 36 cited files anyway.

## Phase 5: levers aimed at where the cost is (done)

- [x] Cost breakdown of phase 4: cache writes 46%, output 38%, cache reads 16%.
- [x] 5c low effort: cost ×0.71 [0.65–0.77], no quality loss. Works.
- [x] 5b reviewed + trusted memory: cost ×0.82 [0.74–0.92] vs no memory,
      score −0.035 (within margin). Works; unreviewed memory still doesn't.
- [x] 5a outline-first reads: ×0.91 [0.83–1.00]. Inconclusive.

## Phases 6-7: the levers combined (done)

- [x] Service first vs plain agent (30 pairs): cost ×0.64, tokens ×0.51, same
      quality. The headline result.
- [x] + low effort: ×0.38, score −0.051 (just past the bar).
- [x] + trusted memory: adds nothing on top of the service (×0.98).
- [x] All three: ×0.28 but score −0.15 (the agent stopped reading files).

## Next: candidates, in order of evidence

- [ ] **The middle ground** between service-first (−36%, same quality) and
      service + low effort (−62%, slightly lower quality).
- [ ] **Human-reviewed memory reused several times.**
- [ ] **Robustness**: a second model, a real open-source corpus, an
      independent label and rubric check, and a held-out task set.
- [ ] **Several specialist agents sharing one store**, with per-agent
      telemetry.

## Out of scope until evidence says otherwise

Vector databases, distributed infrastructure, large agent frameworks,
replacing retrieved context with summaries (phase 3d: summaries lost the
details plans needed), and pruning on short tasks (phase 4a: no saving on
Haiku 5.5).
