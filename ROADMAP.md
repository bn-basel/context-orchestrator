# Roadmap

The project moves in phases separated by decision gates. A phase that adds
features starts only when the previous gate's evidence supports it, and a
negative result is written up rather than worked around.

```
Phase 0  foundation ─▶ Phase 1  measure retrieval ─▶ Gate 1 ─▶ Phase 1b  larger corpus ─▶ Gate 1 again
   ─▶ Phase 2  agent comparison ─▶ Gate 2 ─▶ Phase 3  agent access ─▶ Phase 4  scale up
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

## Phase 1b: a corpus where the question matters (next)

The sample corpus is ~2.6k tokens, smaller than one Claude Code turn's
harness overhead, so phase 2 on it cannot show savings.

- [ ] Choose the corpus: a larger synthetic fixture (controllable, easy to
      label) or a pinned snapshot of a real open-source repository (more
      credible, needs a compatible licence). Target: at least 20× the current
      size.
- [ ] 15–25 labelled tasks on it, committed before running.
- [ ] Re-run gate 1 on the new corpus.
- [ ] Optional, measured as separate configurations: a higher
      `per_kind_limit` (addresses the T02 miss) and a package-size/recall
      sweep over `max_tokens`.

## Gate 1 (re-check on the larger corpus)

Criteria in [benchmarks/gate1.json](benchmarks/gate1.json). If it fails,
improve retrieval and re-measure before phase 2.

## Phase 2: agent comparison

- [ ] Benchmark runner for strategies A (full context) and B (on-demand
      retrieval), then C (no context) and D (oracle), via `claude -p` with the
      isolation flags in the methodology. Raw results as JSONL.
- [ ] Verify what user-level context loads under those flags on a subscription.
- [ ] Hidden test suites per task for objective success.
- [ ] Versioned price table with source and date, kept separate from the
      CLI's `costUSD`.
- [ ] Analysis from raw files only: per-task medians and spreads.

## Gate 2

Does on-demand retrieval use fewer tokens at the same task success? Either
answer is written up and published.

## Phase 3: real agent access

- [ ] MCP server exposing `request_context` with the same schema.
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
