# Context Orchestrator

An experiment in giving coding agents **only the project context they need**,
on demand and with sources, and **measuring** whether that is actually cheaper
than letting them explore or handing them everything.

It includes a small context service (SQLite, keyword and optional
meaning-based search, exposed to agents as an MCP tool) and the benchmark
harness used to test it with Claude Code. Results are summarised below and
told in full in [docs/findings.md](docs/findings.md).

## Results at a glance

300 Claude Code runs (Haiku 4.5) on a synthetic ~140k-token project, 20
realistic tasks, plans graded against rubrics fixed before the runs. Each
strategy is compared, per task, with the agent exploring files on its own:

| Strategy | Input tokens | Cost (API-equivalent) | Plan quality |
|---|---|---|---|
| **Context service, agent told to use it first** | **0.78×** | **0.79×** | no detectable difference |
| Context service, merely offered | 0.90× (n.s.) | 0.93× | no detectable difference |
| Whole project in the prompt | 5.1× | 2.0× | slightly higher (borderline) |
| Oracle: exactly the needed pieces | 0.39× | 0.57× | slightly higher (borderline) |

- **The service saves about a fifth of the cost**, but only when the agent is
  told to use it. Offered, it was skipped in 18 of 60 runs.
- **Full context is the expensive way to a small gain.** The whole project is
  re-sent on every turn.
- **Most input cost is old tool output re-sent on every turn.** Replaying the
  recordings suggests that pruning it in place could cut input tokens by a
  third to a half. That is untested so far; it needs an agent loop that can
  edit its own context.
- **Several ideas did not help:** compact excerpts, "trust the excerpts"
  instructions, and a reader sub-agent (worse: 1.27× tokens, lower quality).

**Limits:** one synthetic corpus, one small model, regex-graded plans and
small samples. Costs are the CLI's API-list-price estimates, not subscription
charges. Read [docs/findings.md](docs/findings.md) before quoting numbers.

## What the service does

Agents send a **typed request** (the task, the kinds of knowledge wanted, a
token budget) and get back a **context package**:

- **Verbatim excerpts** with file paths, line ranges and file hashes, so every
  item can be checked and detected as stale.
- **Trust labels:** `verified`, `observed` (read from source), `unverified`,
  `assumption`. `superseded` decisions are withheld unless asked for.
- **Honest gaps:** requested kinds with nothing relevant are listed as
  unresolved, never filled in.
- **Telemetry:** one event per request; every number says whether it was
  measured, estimated or unavailable. Task text is excluded by default.

```
project files ──ingest──▶ memory (SQLite + FTS5 [+ vectors]) ◀── retrieval (BM25 / hybrid, follow-up hop)
agent ──request_context (MCP) / CLI / Python──▶ orchestrator ──▶ context package ──▶ agent
                                                     └──▶ telemetry (JSONL)
```

Design decisions and trade-offs: [docs/architecture.md](docs/architecture.md).

## Install

Python 3.11+. The core has **no runtime dependencies** (standard library
`sqlite3` with FTS5). Meaning-based search is optional and uses a local
[Ollama](https://ollama.com) with `nomic-embed-text`; nothing leaves the
machine.

```bash
git clone https://github.com/bn-basel/context-orchestrator.git
cd context-orchestrator
uv sync
```

## Use it

```bash
uv run ctxo ingest path/to/project
uv run ctxo request path/to/project --task "Why are refunds wrong after a closure?" --kind decision --kind known_issue --kind code --format markdown
```

As a tool for Claude Code (or any MCP host), add an MCP config such as:

```json
{"mcpServers": {"ctxo": {"command": "uv", "args": ["run", "--directory", "path/to/context-orchestrator", "ctxo", "mcp", "path/to/project"]}}}
```

Useful options: `--retrieval hybrid` (needs Ollama), `--hops 2` (search again
for what the first results name), `--detail compact`, `--max-tokens N`.

From Python:

```python
from context_orchestrator import ContextService, ContextRequest, InfoKind

with ContextService("examples/sample_project") as svc:
    svc.ingest()
    package = svc.request(
        ContextRequest(
            task="Cap overdue fines at the book's replacement cost",
            kinds=[InfoKind.DECISION, InfoKind.CONSTRAINT, InfoKind.CODE],
        )
    )
    print(package.render_markdown())
```

Markdown front matter (`kind:`, `status:`) lets a project label its own
documents; otherwise kinds are inferred from paths (`decisions/` → decision,
`*.sql` → schema, `tests/` → test, …).

## Reproduce the experiments

Everything runs from committed task suites and writes raw results to
`benchmarks/results/<run>/`. Retrieval evaluations make no model calls.
Agent runs call `claude -p` and **use real Claude usage**: start small.

```bash
uv run pytest
uv run ctxo eval-retrieval benchmarks/tasks/hallpass.json --gate benchmarks/gate1.json
uv run ctxo eval-agent benchmarks/tasks/hallpass.json --rubrics benchmarks/tasks/hallpass.rubrics.json --tasks H01,H06 --strategies B2,C --reps 1
uv run ctxo analyze-agent benchmarks/results/<run>
uv run ctxo analyze-traces benchmarks/results/<run> --suite benchmarks/tasks/hallpass.json
uv run ctxo what-if benchmarks/results/<run> --suite benchmarks/tasks/hallpass.json
```

The method is in [docs/benchmark-methodology.md](docs/benchmark-methodology.md),
and every run with its numbers and caveats is in
[benchmarks/README.md](benchmarks/README.md).

## Repository layout

```
src/context_orchestrator/
  memory/            file discovery, structure-aware chunking, SQLite store
  retrieval/         BM25, hybrid (embeddings + rank fusion), follow-up hops, references
  orchestrator/      request → package (budget, trust labels, staleness, gaps)
  agent_interface/   Python API, `ctxo` CLI, MCP server
  telemetry/         JSONL events with metric provenance
  evaluation/        retrieval scoring, agent runner, paired analysis, trace analysis, what-if replay
benchmarks/          corpus (synthetic "Hallpass" project), tasks, rubrics, raw results
examples/            a small sample project
docs/                findings, architecture, benchmark methodology
tests/               unit and end-to-end tests (no model calls)
```

## Status

Research code: tested, but young. See [ROADMAP.md](ROADMAP.md) for what is
done and what is open, and [docs/findings.md](docs/findings.md) for what to
try next.

## License

[MIT](LICENSE)
