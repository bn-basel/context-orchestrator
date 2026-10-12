# Handoff

Development notes for resuming work in a new session. Keep them current:
update at the end of every milestone and before a session's context runs out.

**Last updated:** 2026-10-12. Phases 0–7 done and written up (README,
docs/findings.md, chart); repository public.

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
| 4 Pruning + memory | 4a done: pruning gave no saving on Haiku 5.5 (cost ×1.17, 10 runs, $0.07); 4b memory: findings accurate and served, but no saving (cost ×0.98 pooled over 20 pairs; agents re-open cited files) |
| 5 Levers by cost share | done: low effort ×0.71 (works); reviewed + trusted memory ×0.82 vs no memory (works, score −0.035); outline-first reads ×0.91 (inconclusive); 120 runs, $0.47 |
| 6–7 Combined | done: service first vs plain ×0.64 cost, ×0.51 tokens, same quality (the README headline); + low effort ×0.38 but score −0.051; + trusted memory adds nothing; all three ×0.28 but score −0.15; 105 runs, $0.52 |
| Publication | **public since 2026-10-11** at github.com/bn-basel/context-orchestrator (fresh repository with the cleaned history); the pre-rewrite repository is kept private as bn-basel/context-orchestrator-private-archive (still holds the old commits with the personal email: never make it public). Charts: `benchmarks/charts/results_chart.py` writes docs/img/results-*.svg (simple, README) and results-detail-*.svg (every result, docs/findings.md) |

The full story with numbers: [docs/findings.md](docs/findings.md); every run
with caveats: [benchmarks/README.md](benchmarks/README.md).

## Next step: open (phase 5 done)

Phase 4 log (all in benchmarks/README.md, "Phase 4"):

- Probe confirmed the OpenRouter key (limit $5; the key is in the
  git-ignored `.env`, never open or print it) and that OpenRouter reports
  the charge inside each response's usage. Use **Claude Haiku 5.5** only
  (`anthropic/claude-haiku-5.5`); the owner said never to use Haiku 4.5.
- 4a pruning (run `20261011T071428Z-loop-prune`, 10 runs, $0.067): tokens
  ×0.95, cost ×1.17. No saving; not scaled.
- 4b memory (runs `20261011T072205Z-loop-memory`, 15 runs, $0.093, and
  `20261011T073027Z-loop-memory`, 45 runs, $0.274): pooled over 20 pairs,
  cost ×0.98 [0.90–1.09], scores equal. Findings were accurate, but agents
  opened 30 of 36 cited files anyway.
- Spent on the key after phase 4: $0.43 of $5 (sum of per-response charges;
  the key's own usage counter lags a few calls behind, so don't read totals
  from it).

Phase 5 (2026-10-12, benchmarks/README.md "Phase 5"): runs
`20261012T022153Z-loop-prune` (L/LC/LE, 30 runs, $0.160),
`20261012T023255Z-loop-trust` and `20261012T024550Z-loop-trust` (TR/TU/T0,
30 + 30 runs, $0.158 + $0.154). The 4b findings were reviewed by Claude, not
a person (`tasks/hallpass_followups.findings.json`). Analysis:
`benchmarks/memory_analysis.py --arm X --base Y <runs>`. Spent on the key so
far: about $0.91 of $5.

Phases 6–7 (2026-10-12): runs `20261012T034938Z-loop-combo` (L/S/X, 45
runs, $0.212) and `20261012T050712Z-loop-combo` (L/S/SE/TR, 60 runs,
$0.308). The README leads with service-first vs plain, pooled over both. In
total about $1.42 of the $5 key is used.

Candidates, if the owner wants more:

1. **The middle ground** between service first (−36%, same quality) and
   service + low effort (−62%, slightly lower quality); **human-reviewed**
   memory reused across several follow-ups.
2. **Robustness:** a real open-source corpus, a larger model, longer tasks,
   an independent label and rubric check.
3. **Publication:** done (public). The owner plans social media posts; a PNG
   of the chart may be wanted.

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

- **History was rewritten on 2026-10-11** (before going public) to replace
  the personal commit email with the GitHub no-reply address. Run records cite
  the old commit IDs; `docs/commit-map.txt` maps them. Commit as `bn-basel`
  with that no-reply address (this repository's local git config).

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
