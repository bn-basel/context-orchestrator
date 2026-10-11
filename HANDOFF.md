# Handoff

Development notes for resuming work in a new session. Keep them current:
update at the end of every milestone and before a session's context runs out.

**Last updated:** 2026-10-11. Phases 0–3d done; phase 4 built (runs pending); repository prepared for
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
| 4 Pruning + memory | built: own agent loop with pruning, anchored findings (record_finding), 5 follow-up tasks; offline ceiling recall 0.24 → 0.45; runs need the owner's OpenRouter key |
| Publication | README (tested / found / think), results chart (docs/img), findings, architecture; repository private until the owner decides |

The full story with numbers: [docs/findings.md](docs/findings.md); every run
with caveats: [benchmarks/README.md](benchmarks/README.md).

## Next step: phase 4 runs (built and committed; waiting for the owner's key)

Everything for phase 4 is built and tested offline; plan and pre-selected
tasks are in benchmarks/README.md ("Phase 4 plan"). Order:

1. The owner creates an OpenRouter key **capped at $5** (limit set on
   openrouter.ai) and pastes it into the repository's `.env` file
   (`OPENROUTER_API_KEY=...`; git ignores `.env`, template in `.env.example`).
   The environment variable of the same name also works and wins. Never ask
   for the key in chat, and never open, print or copy `.env`. Subscription
   logins can't drive our own loop (Anthropic's terms limit them to Claude
   Code).
2. `uv sync --group loop`, then `uv run ctxo loop-probe` (one tiny call):
   check that the model id resolves, usage includes cache fields, the
   measured cost lookup works and the key shows a limit.
3. **4a pruning, 10 runs** (L vs LP on H17, H13, H11, H19, H09). Expected
   roughly $0.3–0.8 (estimate: our loop's system prompt is far smaller than
   Claude Code's). Tell the owner the count and estimate before starting.
4. **4b memory, 15 runs** (5 parent runs, 5 follow-ups on memory, 5 on an
   empty one). Similar cost per run.
5. Only after a clear signal: more runs, or hybrid retrieval for findings.

Other candidates: robustness (a second model, a real open-source corpus, an
independent label and rubric check). A "file map" for targeted reads was
estimated at most −8% and not run. The original 20 tasks barely share needed
context (at most 1 labelled section per pair), which is why 4b has its own
follow-up tasks.

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
