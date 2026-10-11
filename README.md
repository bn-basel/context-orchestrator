# Context Orchestrator

An experimental context service for AI agents working on software projects.

Instead of giving every agent the whole project history, a project-wide
service keeps the project's knowledge (decisions, schemas, conventions, code,
tests, known bugs) and answers **structured context requests** with a compact,
**source-referenced** context package. Agents ask for what their current task
needs; the service says where every piece came from, how far it can be
trusted, and what it could not find.

> **Status: early experiment.** The retrieval pipeline works end to end and is
> tested. Retrieval quality has been measured once, on a small synthetic
> corpus (recall 0.83, precision 0.40; details and caveats in
> [benchmarks/README.md](benchmarks/README.md)). Whether this approach saves
> tokens or improves task quality compared with handing an agent the full
> context is **not yet measured**; see
> [docs/benchmark-methodology.md](docs/benchmark-methodology.md).

## The problem

Agents working on a codebase either get too little context (and guess) or too
much (and pay for it in tokens, latency and distraction). A common middle path
is retrieval. This project explores a specific version of it:

- one **persistent memory** per project, shared by several specialist agents;
- **typed requests** ("decisions and schema relevant to task X, under
  constraint Y") rather than free-text search;
- **provenance first**: every item carries file, line range and file hash, so
  it can be checked and detected as stale;
- **honest gaps**: missing information is reported as unresolved, never filled
  in, and assumptions are labelled as assumptions;
- **measurement built in**: every request emits a telemetry event, and every
  number records whether it was measured, estimated or unavailable.

None of these ideas is new on its own. The goal is a small, inspectable
system in which their costs and benefits can be measured.

## How it works

```
project files ──ingest──▶ memory (SQLite + FTS5) ◀──search── retrieval (BM25)
                                                        ▲
agent ──ContextRequest──▶ agent_interface ──▶ orchestrator ──▶ ContextPackage ──▶ agent
                                                        │
                                                        └──▶ telemetry (JSONL)
```

1. **Ingest.** Markdown, Python, SQL and config files are split into chunks:
   Markdown by heading, Python by top-level `def`/`class`, SQL by `CREATE`
   statement. Each chunk keeps its exact line range and the file's SHA-256.
   Markdown front matter can declare `kind` and `status`.
2. **Request.** An agent sends a `ContextRequest`: the task, the kinds of
   information it wants, any constraints, and a token budget.
3. **Retrieve.** For each requested kind, BM25 keyword search (SQLite FTS5
   with Porter stemming) finds candidates and records which terms matched.
4. **Package.** Candidates are selected round-robin across kinds within the
   token budget. Superseded decisions are set aside, and source files are
   re-hashed to flag stale items. Kinds with no match are listed as
   unresolved.
5. **Record.** One telemetry event per request: counts, sources, measured
   latency, and the package size (an estimate). Task text is excluded by
   default.

Details and trade-offs: [docs/architecture.md](docs/architecture.md).

### Information kinds and trust levels

| `kind` | Inferred from (unless front matter says otherwise) |
|---|---|
| `decision` | Markdown under `decisions/` or `adr/` |
| `schema` | `*.sql` |
| `code` | source files (`.py`, `.js`, `.ts`, …) |
| `test` | `tests/`, `test_*.py` |
| `dependency` | `pyproject.toml`, `package.json`, `requirements.txt`, … |
| `convention`, `constraint`, `known_issue`, `finding` | front matter only |
| `doc` | any other Markdown or text |

| `status` | Meaning |
|---|---|
| `verified` | the document declares it has been checked |
| `observed` | read directly from a source file: shows what exists, not that it is correct |
| `unverified` | Markdown that declares no status |
| `assumption` | declared as an unconfirmed assumption; flagged in the package notes |
| `superseded` | replaced by a later decision; omitted unless requested |

## Installation

Requires Python 3.11+. The core has **no runtime dependencies** (standard
library `sqlite3` with FTS5).

```bash
git clone https://github.com/bn-basel/context-orchestrator.git
cd context-orchestrator
uv sync            # or: python -m venv .venv && pip install -e . pytest ruff
```

## Usage

### Command line

```bash
uv run ctxo ingest examples/sample_project
```

```bash
uv run ctxo request examples/sample_project --task "Fix BUG-12 so a book returned one hour late is not charged a full day's fine" --kind known_issue --kind code --kind test --kind finding --format markdown
```

`--format json` (the default) returns the full package for programmatic use.
A request can also come from a file: `--request-file examples/requests/fix-bug-12.json`.
State goes to `<project>/.ctxo/` (or `--state-dir`); project files are only
read, never written.

### Python

```python
from context_orchestrator import ContextService, ContextRequest, InfoKind

with ContextService("examples/sample_project") as svc:
    svc.ingest()
    package = svc.request(
        ContextRequest(
            task="Cap overdue fines at the book's replacement cost",
            kinds=[InfoKind.DECISION, InfoKind.CONSTRAINT, InfoKind.CODE],
            constraints=["money is integer cents"],
            max_tokens=2000,
        )
    )
    for item in package.items:
        print(item.source.label(), item.kind, item.status, item.matched_terms)
    print(package.unresolved)
```

### Response shape

Abridged output of `ctxo request examples/sample_project --request-file
examples/requests/fix-bug-12.json` (first of 8 items; text, hash and ids
shortened):

```json
{
  "request_id": "733c81df…",
  "task": "Fix BUG-12 so a book returned one hour late is not charged a full day's fine",
  "items": [{
    "kind": "known_issue",
    "status": "verified",
    "heading": "Known issues > BUG-12: days_overdue counts a partial day as a full day",
    "text": "# Known issues\n\n## BUG-12: days_overdue counts a partial day as a full day\n…",
    "source": {"path": "docs/known-issues.md", "line_start": 5, "line_end": 11,
               "file_sha256": "eb684384…", "ingested_at": "2026-10-11T00:24:35+00:00"},
    "score": 17.7164,
    "matched_terms": ["bug", "days", "day", "full", "book", "returned", "hour",
                      "timestamp", "charged", "fine"],
    "stale": false,
    "estimated_tokens": 86
  }],
  "unresolved": ["No finding information matched the task terms. It may be missing from the knowledge base, or described with different vocabulary."],
  "omitted": [],
  "estimated_tokens": {"value": 734, "kind": "estimated",
                       "method": "ceil(chars / 4) heuristic, not a model tokenizer"},
  "query_terms": ["bug", "book", "returned", "hour", "late", "charged", "full", "day", "fine",
                  "money", "integer", "cents", "timestamps", "utc"],
  "notes": []
}
```

## Tests

```bash
uv run pytest
uv run ruff check .
```

Retrieval benchmark (phase 1, no model calls):

```bash
uv run ctxo eval-retrieval benchmarks/tasks/sample_project.json --gate benchmarks/gate1.json
```

The tests run the whole pipeline against
[`examples/sample_project`](examples/sample_project), a synthetic library
lending service with ADRs (one superseded), a schema, conventions, a
constraint, a recorded assumption, known bugs, code and tests. It contains no
`finding` documents on purpose, so the unresolved path is exercised.

## Limitations (current)

- **Keyword retrieval only.** BM25 misses synonyms and paraphrases ("penalty"
  will not find "fine"). It also favours short chunks: in the sample schema
  the one-line `CREATE INDEX … ON loans` outranks the `CREATE TABLE loans` it
  belongs to.
- **Token counts in the service are estimates** (`chars / 4`). Real counts
  come from the model provider's usage data during benchmark runs.
- **No MCP server yet.** Agents use the Python API or the CLI; MCP is the
  planned integration.
- **No memory write path yet.** Agents cannot record findings; the knowledge
  base changes only by editing files and re-ingesting.
- **No agent comparison yet.** Only retrieval has been measured (phase 1),
  on a corpus too small for token savings to matter. The full-context vs.
  retrieval comparison with a model (phase 2) has not been run.
- Status labels are only as good as the front matter people write.

See [ROADMAP.md](ROADMAP.md) for what is implemented and what is planned.

## Repository layout

```
src/context_orchestrator/
  models.py           request/response contract, Metric provenance
  memory/             file discovery, chunking, SQLite store
  retrieval/          BM25 retrieval with matched-term explanations
  orchestrator/       request → package pipeline
  agent_interface/    Python API (ContextService) and CLI (ctxo)
  telemetry/          JSONL events
  evaluation/         retrieval scoring, `claude -p` usage parsing
tests/                unit and end-to-end tests
benchmarks/           labelled task suites, gate criteria, raw run results
examples/             sample project and example requests
docs/                 architecture and benchmark methodology
```

## License

[MIT](LICENSE)
