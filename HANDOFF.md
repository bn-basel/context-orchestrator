# Handoff

Read this first when resuming work in a new session. Keep it current: update
it at the end of every milestone, and before a session's context runs out.

**Last updated:** 2026-10-11, phase 2 full run done and written up.

## Resume prompt

Paste into a new chat opened in `C:\WIP\projects\Agent-Memory`:

> Read HANDOFF.md, ROADMAP.md and benchmarks/README.md, check `git log --oneline -8`
> and `uv run pytest`, then continue with the next step in HANDOFF.md.

## Where we are

| Phase | State |
|---|---|
| 0 Foundation | done: ingest → retrieve → package → telemetry, CLI + Python API |
| 1 Measure retrieval | done on the tiny sample: gate 1 passed narrowly (recall 0.83) |
| 1b Larger corpus | done: Hallpass (~140k tokens, 20 tasks). **Gate 1 not passed**: recall 0.56, precision 0.28, 2 missed "not found" cases |
| 1c Improve retrieval | **done**. Best: hybrid + 2 hops, Hallpass recall 0.61 / precision 0.32; gate 1 (0.80) not reached by any single-request method. **Owner decision pending** |
| 2 Agent comparison | **done**: 300 Haiku runs, ~$31 API-equivalent. B2 (service, used first) 0.79x cost vs C at no detectable quality loss; offered-only B within noise; full context 2x cost. Gate 2 answered for this setting |
| 3–5 | planned, see ROADMAP.md |

Diagnosis (benchmarks/README.md): ranking is the main loss (recall 0.56 →
0.73 when the package grows 3×); ~15% of needed chunks aren't reached even at
23% of the corpus; "not found" can't be detected by zero matches in a big
corpus; the token budget ignores rendering overhead (bug).

## Next step: owner's choice

Phase 2 is written up (benchmarks/README.md, "Phase 2 result"; ROADMAP.md,
"Gate 2" and "Next"). Candidate next steps, in order of evidence:

- **Better retrieval recall**: the oracle saves ~60% of tokens, the service
  ~20%. Ideas: let the agent decompose the task into several requests, better
  follow-ups, a reranker. Measure on phase 1 first (cheap), then re-run B2.
- **Robustness**: repeat phase 2 with Sonnet and/or a second corpus;
  independent label/rubric check.
- **Make it public**: repository is private; ask the owner before changing.

Commands: `ctxo eval-agent ... --resume <run folder>` continues an interrupted
run; `ctxo analyze-agent <run folder>` recomputes the paired analysis.

Embedding setup if needed again: start the toolbox Ollama with
`OLLAMA_MODELS=C:\WIP\tools\ollama\models C:\WIP\tools\ollama\ollama.exe serve`;
`nomic-embed-text` is pulled. Then use `--retrieval hybrid`.

## Decisions already made (do not re-ask)

- Repo: https://github.com/bn-basel/context-orchestrator, **private**, MIT,
  owner account `bn-basel`.
  **Ask before making it public.**
- Standard library only at runtime; dev tools via `uv`. No vector DB or agent
  framework unless measurements justify it.
- Gate 1 thresholds were set by Claude and committed before the first run
  (`060b7fb`). Don't change them after seeing results; add a new gate file if
  the criteria need revising, and say why.
- The full corpus counts as strategy A's context; phase 2 compares A, B, C, D
  as described in the methodology.
- Phase 1b corpus is **synthetic** (owner's choice over downloading Starlette).
  Bias guards: four separate authoring agents, spec kept outside the corpus,
  a fifth agent writes tasks seeing only the corpus. Reuse this pattern for
  the held-out set.
- Gate 1 criteria stay as committed; don't relax them after seeing results.
- `min_relative_score` and `max_references` exist but default to off (no net
  gain measured). Standard NLTK stopwords and the rendered-package budget are on.

## Facts learned the hard way

- `claude -p --output-format json` gives per-model input, output, cache-read,
  cache-write and thinking tokens, plus `costUSD` with `costBasis: "list"`
  (an API-price equivalent, **not** the subscription charge). A one-word reply
  used ~35k input tokens of harness overhead.
- `claude --bare` only authenticates with `ANTHROPIC_API_KEY`, so it can't be
  used on the subscription. Isolation flags for subscription runs are listed
  in the methodology; still unverified: whether `~/.claude/CLAUDE.md` loads
  under them.
- Global git `core.autocrlf=true`; `.gitattributes` forces LF so fixture file
  hashes are identical on every OS. Keep it.
- Writing the corpus with four agents cost ~1.06M subagent tokens, and the
  task writer ~0.4M. Brief agents tightly; they overshoot size targets (~2×).
- The evaluator's dirty flag counts tracked changes only (untracked run folders
  are ignored). It records git state at the start of a run. Run it from a clean
  tree; scratch runs go to `--out benchmarks/scratch` (git-ignored).
- Changing `examples/sample_project` breaks label line ranges. `load_suite`
  validates them and a test fails loudly; update the labels in the same commit.

## Working rules (owner's)

- Short, plain reports. The owner dictates by voice, so expect transcription slips.
- Never permanently delete files: move them to the Recycle Bin.
- Free, local tools only; state size and source before big downloads.
- Don't claim anything succeeded without verifying it; numbers must say
  measured / estimated / unavailable.

## Verify the state quickly

```bash
git log --oneline -8
uv run pytest
uv run ruff check .
uv run ctxo eval-retrieval benchmarks/tasks/sample_project.json --gate benchmarks/gate1.json --out benchmarks/scratch
```
