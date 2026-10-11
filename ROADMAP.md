# Roadmap

The project moves in phases separated by decision gates. A phase that adds
features starts only when the previous gate's evidence supports it, and a
negative result is written up rather than worked around.

```
Phase 0  foundation ─▶ Phase 1  measure retrieval ─▶ Phase 1b  larger corpus ─▶ Phase 1c  improve retrieval
   ─▶ Gate 1 (single request: not passed) ─▶ Phase 2  agent comparison ─▶ Gate 2 (answered for one setting)
   ─▶ Phase 3  agent access ─▶ Phase 4  scale up
   ─▶ Phase 5  smarter search (only if evidence demands it)
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

## Next: candidates, in order of evidence

- [ ] **Better retrieval recall** (the oracle shows ~60% token savings are
      possible; the service reaches ~20%): e.g. task decomposition by the
      agent, smarter follow-ups, a reranker.
- [ ] **Robustness of the phase 2 result**: a second model (Sonnet), a second
      corpus, an independent rubric/label check.
- [ ] **Held-out task set** for the retrieval configuration.

## Phase 3: real agent access

- [x] MCP server exposing `request_context` (`ctxo mcp`; built for phase 2).
- [ ] Memory write path: agents propose findings, stored with provenance and
      status, applied only after explicit review (no silent writes).

## Phase 4: scale up

- [ ] Several specialist agents sharing one store, with per-agent telemetry.
- [ ] Larger and more varied corpora.

## Phase 5: smarter search (conditional)

- [ ] Hybrid retrieval (BM25 + embeddings), **only if** measurements show
      vocabulary mismatch matters (phase 1 T07 is the first data point),
      compared against the BM25 baseline on the same suite.

## Out of scope until evidence says otherwise

Vector databases, distributed infrastructure, large agent frameworks, and
automatic summarisation of retrieved context.
