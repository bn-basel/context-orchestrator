# Roadmap

## Implemented (v0.1)

- [x] Ingest Markdown, Python, SQL and config files into SQLite, incrementally
      by file hash; one state directory, project files never written.
- [x] Structure-aware chunking with exact line ranges and file hashes.
- [x] Front matter `kind` / `status`; kind inference from paths.
- [x] BM25 keyword retrieval (FTS5, Porter stemming) with matched-term
      explanations and per-kind filtering.
- [x] Context packages: round-robin token budget across kinds, superseded
      items omitted with a reason, assumptions flagged, stale sources
      detected, unresolved kinds reported.
- [x] Python API (`ContextService`) and CLI (`ctxo ingest`, `ctxo request`).
- [x] JSONL telemetry per request; task text excluded by default; every
      metric labelled measured / estimated / unavailable.
- [x] Parser for `claude -p --output-format json` usage (tested against a real
      captured result).
- [x] Synthetic sample project and 40 unit and end-to-end tests.

## Next milestone: v0.2, a first measurable comparison

Smallest step that can produce real evidence:

- [ ] Write 5–8 benchmark tasks against the sample project, each with hidden
      tests and hand-labelled relevant chunks.
- [ ] Retrieval-only evaluation (no LLM): precision and recall of `ctxo`
      against the labels. Cheap, deterministic, and it shows whether
      retrieval is worth testing with a model at all.
- [ ] Benchmark runner for strategies A and B (then C and D) using `claude -p`
      with the isolation flags in the methodology; raw results stored as
      JSONL.
- [ ] Verify which user-level context (`~/.claude/CLAUDE.md`, auto-memory) is
      loaded under the isolation flags on a subscription.
- [ ] Versioned price table with source and date; cost recomputation kept
      separate from the CLI's `costUSD`.
- [ ] Analysis script producing per-task medians from raw files only.

## Planned, not started

- [ ] MCP server exposing `request_context` with the same schema, so agents
      call the service as a tool instead of through the CLI.
- [ ] Memory write path: agents propose findings, stored with provenance and
      status, applied only after explicit review (no silent writes).
- [ ] Multi-agent scenario: several specialist agents sharing one store, with
      per-agent telemetry.
- [ ] Larger and more realistic fixture corpora.
- [ ] Hybrid retrieval (BM25 + embeddings), **only if** the evaluation shows
      vocabulary mismatch is a significant failure mode; compared against
      the BM25 baseline.

## Explicitly out of scope until evidence says otherwise

Vector databases, distributed infrastructure, large agent frameworks, and
automatic summarisation of retrieved context.
