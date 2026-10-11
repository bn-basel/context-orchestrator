# Handoff

Development notes for resuming work in a new session. Keep them current:
update at the end of every milestone and before a session's context runs out.

**Last updated:** 2026-10-11. Phases 0–3d done; repository prepared for
publication (still private); next direction open.

## Resume prompt

Paste into a new session opened in the repository folder:

> Read HANDOFF.md, ROADMAP.md, docs/findings.md and benchmarks/README.md,
> check `git log --oneline -8` and `uv run pytest`, then continue with the
> next step in HANDOFF.md.

## Where we are

| Phase | State |
|---|---|
| 0 Foundation | done: ingest → retrieve → package → telemetry; CLI, Python API |
| 1 / 1b / 1c Retrieval | done: realistic corpus (Hallpass, ~140k tokens, 20 tasks); best single-request recall 0.61 (hybrid + 2 hops); gate 1 (0.80) not passed |
| 2 Agent comparison | done: 300 Haiku runs; service used first (B2) 0.79× cost vs exploring alone, no detectable quality loss; full context 2× cost |
| 3a–3d | done: compact excerpts (no agent benefit), trace analysis (35% re-reads), what-if replay (pruning −33% to −53%, untested), reader sub-agent (worse) |
| Publication | README (tested / found / think), results chart (docs/img), findings, architecture; repository private until the owner decides |

The full story with numbers: [docs/findings.md](docs/findings.md); every run
with caveats: [benchmarks/README.md](benchmarks/README.md).

## Next step: open

Candidates, in order of evidence (see docs/findings.md, "What would move this
forward"):

1. **In-place context pruning** with an agent loop that can edit its own
   context (Claude API context editing, `clear_tool_uses`). Largest estimated
   saving. Needs API access with usage billing, which the owner must approve.
   **Blocked (2026-10-11):** no API credentials on the machine; the owner
   must create an API key and set `ANTHROPIC_API_KEY` themselves.
   (A "file map" for targeted reads was estimated at most -8% and not run.)
2. **Multi-task benchmark** with a memory write path: agents record verified
   findings so later tasks on the same project start ahead.
3. **Robustness:** a second model, a real open-source corpus, an independent
   label and rubric check.

## Rules for experiments

- **Agent runs consume real model usage** (the 300-run benchmark was costly).
  Start tiny (~10 runs), scale only on a clear signal, and state the run count
  and expected usage before starting. Do retrieval work offline first
  (`ctxo eval-retrieval`, no model calls).
- **Mind the noise.** Single runs vary about ×1.7 in tokens. ~18 runs detect a
  50% saving; ~160 are needed for 20%. Prefer behaviour measures from traces
  (`ctxo analyze-traces`).
- **Commit before you run.** Labels, rubrics and gate criteria are committed
  before the runs that use them. Run from a clean tree, and never edit files
  under `benchmarks/results/`.
- **Keep the gates.** Gate 1 criteria stay as committed; revise via a new gate
  file with a stated reason.

## Facts learned the hard way

- `claude -p --output-format json` reports per-model input, output,
  cache-read, cache-write and thinking tokens, plus `costUSD` with
  `costBasis: "list"`: an API-price equivalent, **not** a subscription charge.
  `modelUsage` includes sub-agents; `result.usage` covers the main agent only.
- `claude --bare` only authenticates with an API key. The isolation flags used
  instead are listed in docs/benchmark-methodology.md.
- **Sub-agents** (Claude Code 2.1.292) run in the background unless told to
  run in the foreground. A custom sub-agent's tools must also be enabled for
  the session, or it refuses to start.
- **Line endings.** Git `core.autocrlf` may be on; `.gitattributes` forces LF
  so fixture hashes match on every OS.
- **Changing fixtures breaks labels.** Edits to `examples/sample_project` or
  the Hallpass corpus shift labelled line ranges. `load_suite` validates them.
- **Hybrid retrieval and strategies B/B2** need a local Ollama with
  `nomic-embed-text` running before the run starts.
- Generating the corpus with four agents cost ~1.06M sub-agent tokens; brief
  agents tightly, since they overshoot size targets (~2×).

## Verify the state quickly

```bash
git log --oneline -8
uv run pytest
uv run ruff check .
uv run ruff format --check .   # CI runs this too (it also formats Markdown code blocks)
uv run ctxo eval-retrieval benchmarks/tasks/sample_project.json --gate benchmarks/gate1.json --out benchmarks/scratch
```
