# Handoff

Read this first when resuming work in a new session. Keep it current: update
it at the end of every milestone, and before a session's context runs out.

**Last updated:** 2026-10-11, end of phase 1b.

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
| 1c Improve retrieval | **next** |
| 2 Agent comparison | designed in docs/benchmark-methodology.md, not built |
| 3–5 | planned, see ROADMAP.md |

Diagnosis (benchmarks/README.md): ranking is the main loss (recall 0.56 →
0.73 when the package grows 3×); ~15% of needed chunks aren't reached even at
23% of the corpus; "not found" can't be detected by zero matches in a big
corpus; the token budget ignores rendering overhead (bug).

## Next step (phase 1c)

1. Treat `benchmarks/tasks/hallpass.json` as the **development set**. Improve
   retrieval in small, separately measured steps (candidates and order in
   ROADMAP.md, phase 1c). Commit each change, then run
   `ctxo eval-retrieval benchmarks/tasks/hallpass.json --gate benchmarks/gate1.json`
   from a clean tree and commit the run folder.
2. Keep the old default run as the baseline; never overwrite results.
3. When changes are frozen, have a **fresh agent** write a held-out suite
   (`benchmarks/tasks/hallpass-holdout.json`) the same way as before (it sees
   only the corpus and the format example; commit before running). Judge
   gate 1 on that suite.
4. Embeddings (hybrid search) only if the cheap fixes stall. They need a model
   download, so ask the owner first.

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
