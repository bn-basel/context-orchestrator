# Architecture

This document explains how v0.1 is built and why. It describes what exists;
planned work is in [ROADMAP.md](../ROADMAP.md).

## Goals and non-goals

**Goals for v0.1:** a small, deterministic, fully inspectable pipeline from
project files to a source-referenced context package, with telemetry designed
for later benchmarking.

**Non-goals for v0.1:** semantic search, vector databases, distributed
deployment, agent frameworks, automatic memory writes. Each can be added once
the evaluation shows a need for it.

## Module map

| Module | Responsibility | Key types |
|---|---|---|
| `models` | Request/response contract; provenance of numbers | `ContextRequest`, `ContextPackage`, `ContextItem`, `SourceRef`, `Metric` |
| `memory` | Discover and chunk files; persist chunks and hashes in SQLite | `MemoryStore`, `IngestReport`, `load_file` |
| `retrieval` | BM25 keyword search with matched-term explanations | `LexicalRetriever`, `ScoredChunk`, `extract_terms` |
| `orchestrator` | Request → package: per-kind retrieval, budget, staleness, gaps | `ContextOrchestrator` |
| `agent_interface` | What agents call: Python facade and `ctxo` CLI | `ContextService`, `cli.main` |
| `telemetry` | One JSONL event per request; privacy-preserving defaults | `JsonlTelemetry`, `context_request_event` |
| `evaluation` | Retrieval scoring against labelled tasks; `claude -p` usage parsing | `load_suite`, `run_suite`, `parse_claude_cli_result` |

Dependencies point one way: `agent_interface → orchestrator → retrieval →
memory → models`, with `telemetry` used by the orchestrator. `models` imports
nothing from the package.

## Key decisions

### D1. Standard library only: SQLite + FTS5

SQLite gives one-file persistence, transactions and, through FTS5, a BM25
full-text index with Porter stemming. That covers storage and retrieval
without a server, a model download or a dependency. Trade-off: no semantic
matching (see D3).

### D2. Chunk by document structure, keep exact line ranges

Markdown is split at `#`/`##` headings (a heading with no body is folded into
the next section), Python at top-level `def`/`class` via `ast`, and SQL at
`CREATE` statements. Everything else uses 60-line windows. A chunk's text is
always the exact source lines `line_start..line_end`; it is never rewritten
or summarised. That keeps provenance exact and testable (a test asserts this
for every chunk). Trade-off: chunks can be small and miss surrounding context.
Section headings carry their document title (`ADR 0004 … > Decision`) to
reduce that.

### D3. Lexical retrieval first, with explanations

BM25 is deterministic and every hit can be explained by `matched_terms`
(taken from FTS5 `highlight()`), which makes retrieval failures diagnosable.
Known weaknesses, kept visible on purpose: vocabulary mismatch ("penalty" vs
"fine"), stemming collisions, and a bias toward short chunks. A semantic or
hybrid retriever should be added only if the benchmark shows these failures
matter, and it should be compared against this baseline.

### D4. Typed requests, per-kind retrieval, round-robin budget

A request names the kinds of information it wants. The orchestrator searches
each kind separately and fills the token budget round-robin (best of each
kind first, then second best, …). Without this, one verbose kind such as code
can crowd out a short but critical decision. BM25 scores from the same query
are comparable across kinds because IDF is computed over the whole index.

### D5. Trust levels, and never filling gaps

Each chunk carries a `status`: `verified`, `observed`, `unverified`,
`assumption` or `superseded`. Source files are `observed`: they show what
exists, not that it is right. Superseded decisions are omitted with a reason,
and assumptions are flagged in `notes`. If a requested kind has no match, the
package says so in `unresolved` (and, machine-readably, in `unresolved_kinds`). The service has no code path that generates
text.

### D6. Staleness by hash

Each `SourceRef` records the file's SHA-256 at ingestion. When a package is
built, referenced files are re-hashed (once per file per request). A changed
or deleted file marks its items `stale: true` and adds a note. Cost: one file
read per distinct source per request, which is negligible at this scale.

### D7. Numbers carry their provenance

`Metric(value, kind, method)` with `kind` ∈ {measured, estimated,
unavailable}. In-process latency is measured. Package size is estimated
(`chars / 4`; the service has no tokenizer). A missing provider field is
unavailable, never zero. This is what makes the full-context vs. retrieval
comparison honest.

### D8. Telemetry is privacy-preserving by default

Events contain ids, counts, kinds, source labels and metrics. Task text,
constraints and query terms are stripped unless `record_task_text=True`; a
SHA-256 of the task allows grouping without storing it. Retrieved text is
never logged. A telemetry write failure is logged and does not fail the
request.

### D9. Read-only towards the project

Ingestion only reads project files. All state lives in one directory
(`<project>/.ctxo/` by default, overridable). A test checks that ingestion
leaves every project file's modification time unchanged.

## Data model (SQLite)

```
meta(key, value)                       -- schema_version, project_root
documents(path PK, sha256, kind, status, ingested_at)
chunks(chunk_id PK, path FK→documents ON DELETE CASCADE, kind, status,
       heading, text, line_start, line_end, metadata_json)
chunks_fts  FTS5(chunk_id UNINDEXED, heading, text, path; porter unicode61)
```

BM25 column weights: heading 2.0, text 1.0, path 0.5. Ingestion is
incremental by file hash and runs in a single transaction. A store is bound
to one project root and refuses to ingest a different project.

## Error handling

- Invalid requests (empty task, unknown kind) raise `ValueError`. The CLI exits 1.
- Requesting before ingesting raises `RuntimeError("…Run ingest first.")`.
- Unreadable, non-UTF-8 or oversized (>512 KB) files are skipped and listed in
  the ingest report. Unparseable Python falls back to line windows.
- Logging uses the standard `logging` module per module; `ctxo -v` enables
  debug output on stderr.

## Extension points

- **Retriever.** The orchestrator only needs `search(terms, kind, limit) →
  list[ScoredChunk]`. A semantic retriever can implement the same method.
- **Telemetry sink.** Anything with `emit(dict)`.
- **Agent interface.** An MCP server would be a thin adapter over
  `ContextService.request`, exposing the same request/response schema.
