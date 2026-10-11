# Benchmarks

```
benchmarks/
  tasks/<suite>.json      task suites: tasks + hand-labelled relevant / forbidden line ranges
  gate1.json              pass/fail criteria for gate 1, fixed before the first run
  results/<run-id>/       raw output of each committed run (never edited by hand)
    run.json              metadata: commit, environment, suite hash, config, summary, gate
    results.jsonl         one record per task: scores, returned items, misses
    telemetry.jsonl       the service's own telemetry events for the run
    summary.md            human-readable rendering of the two files above
```

Run the phase 1 retrieval evaluation (no model calls, takes about a second):

```bash
uv run ctxo eval-retrieval benchmarks/tasks/sample_project.json --gate benchmarks/gate1.json
```

Commit the tree first: the run records the commit hash and flags uncommitted
changes. For throwaway runs use `--out benchmarks/scratch` (git-ignored).

Scoring rules are in the docstring of
[`retrieval_eval.py`](../src/context_orchestrator/evaluation/retrieval_eval.py);
the method is in [docs/benchmark-methodology.md](../docs/benchmark-methodology.md).

## Phase 1 result: sample project (run `20261011T004023Z-sample_project`)

Commit `4c38806`, default config (`max_tokens=4000`, `per_kind_limit=3`), 9 tasks.
Labels and gate criteria were committed in `060b7fb`, before the evaluator existed.

| Metric | Value |
|---|---|
| Mean recall | 0.83 (gate ≥ 0.80) |
| Mean precision | 0.40 |
| Superseded items returned | 0 |
| Expected "not found" kinds reported | all |
| Assumptions delivered with their label | all |
| Mean package size | ~576 tokens, 0.22 of the corpus (estimated) |

**Gate 1: passed, narrowly.** What the misses show:

- **T07, vocabulary mismatch (recall 0.25).** "penalty / patrons / items /
  deadline" never meets "fine / members / books / due". The one hit matched
  only the word "after", so the real recall is effectively zero. This is
  BM25's known blind spot, now measured.
- **T03 (recall 0.50).** The key constraint (money is integer cents) was
  missed because the task never says "money" or "cents". The same task
  retrieved an ADR because it says something is "fine for a single desk": a
  homonym false positive.
- **T02 (recall 0.75).** `calculate_fine` ranked fourth among code chunks
  and lost its slot to `per_kind_limit=3`.
- **Precision 0.40.** Most packages carry two or three loosely related items
  for every relevant one. Labels are minimal, so this is pessimistic, but
  the direction is clear.

**Why this does not yet justify phase 2.** The whole corpus is about 2,600
tokens (estimated). That is far less than the ~35k tokens of harness overhead
in a single Claude Code turn. On this fixture, giving an agent everything is
already cheap, so a full-context vs. retrieval comparison cannot show
meaningful savings. Gate 1 is necessary but not sufficient: the next step is
a corpus large enough for the question to matter (see ROADMAP, phase 1b).

Threats specific to this run: one author wrote the fixture, the retriever,
the tasks and the labels; nine tasks is a small sample; T01's output was seen
during development.
