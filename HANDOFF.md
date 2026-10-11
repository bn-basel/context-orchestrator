# Handoff

Read this first when resuming work in a new session. Keep it current: update
it at the end of every milestone, and before a session's context runs out.

**Last updated:** 2026-10-11, end of phase 1.

## Resume prompt

Paste into a new chat opened in `C:\WIP\projects\Agent-Memory`:

> Read HANDOFF.md, ROADMAP.md and benchmarks/README.md, check `git log --oneline -8`
> and `uv run pytest`, then continue with the next step in HANDOFF.md.

## Where we are

| Phase | State |
|---|---|
| 0 Foundation | done: ingest → retrieve → package → telemetry, CLI + Python API |
| 1 Measure retrieval | done: 9 labelled tasks, `ctxo eval-retrieval`, **gate 1 passed narrowly** (recall 0.83 vs. ≥ 0.80, precision 0.40) |
| 1b Larger corpus | **next**: the sample corpus (~2.6k tokens) is too small for phase 2 to mean anything |
| 2 Agent comparison | designed in docs/benchmark-methodology.md, not built |
| 3–5 | planned, see ROADMAP.md |

Phase 1 misses and their causes: vocabulary mismatch (T07, "penalty" vs.
"fine"), a constraint the task text never names (T03), and the per-kind slot
limit (T02). Details: benchmarks/README.md.

## Next step (phase 1b)

1. **Decision needed from the owner:** for the larger corpus, use a bigger
   synthetic fixture (controllable, easy to label) or a pinned snapshot of a
   real open-source repo (more credible; check the licence; state its size
   before downloading). Target: at least 20× the current ~2.6k tokens.
2. Write 15–25 tasks with labels, plus a new suite file in
   `benchmarks/tasks/`. **Commit them before running the evaluator.**
3. Run `ctxo eval-retrieval` on it with `--gate benchmarks/gate1.json` from a
   clean tree, commit the run folder, and write the findings into
   benchmarks/README.md.
4. Optional extra configurations, reported separately and never replacing
   the default run: `--per-kind-limit 4/5`, and a `--max-tokens` sweep.

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
- The evaluator records git state at the start of a run. Run it from a clean
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
