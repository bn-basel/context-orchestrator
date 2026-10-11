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

## Phase 1b result: Hallpass corpus (run `20261011T013257Z-hallpass`)

**Corpus.** A synthetic council booking system written by four separate
authoring agents from a shared spec ([corpora/hallpass.spec.md](corpora/hallpass.spec.md),
kept outside the corpus; known cross-area drift in [corpora/hallpass.notes.md](corpora/hallpass.notes.md)).
163 ingested files, 1,035 chunks, ~140k tokens (estimated): about 54× the
sample project. Committed in `418ac48` before any tasks existed.

**Tasks.** 20 tasks with 107 relevant labels, written by a fifth agent that
read only the corpus (not the spec, the retriever or any results) and phrased
them as real tickets. Committed in `4f93855` before the first run.

**Result at the default config** (`max_tokens=4000`, `per_kind_limit=3`):

| Metric | Value | Gate 1 |
|---|---|---|
| Mean recall | 0.56 | ≥ 0.80: **fail** |
| Mean precision | 0.28 | none |
| Superseded items returned | 0 | pass |
| Expected "not found" kinds reported | 0 of 2 | **fail** |
| Assumptions delivered with their label | all | pass |
| Mean package size | ~3.1k tokens, 0.02 of the corpus (estimated) | pass |

**Gate 1: not passed.** By category, recall is highest for assumption traps
(0.90) and schema tasks (0.75), and lowest for superseded traps (0.30: the
superseded ADR is correctly withheld, but most of the current material is
missed too) and decision-constrained features (0.42).

**Diagnostic sweep** (same commit `2d07cd5`, runs `…013402Z` to `…013410Z`):

| `max_tokens` / `per_kind_limit` | Package (est.) | Share of corpus | Recall | Precision |
|---|---|---|---|---|
| 4000 / 3 (default) | ~3.1k | 2% | 0.56 | 0.28 |
| 4000 / 6 | ~4.5k | 3% | 0.65 | 0.21 |
| 8000 / 6 | ~6.0k | 4% | 0.70 | 0.18 |
| 16000 / 10 | ~9.6k | 7% | 0.73 | 0.12 |
| 200000 / 50 | ~32k | 23% | 0.85 | 0.04 |

What this says:

1. **Ranking is the main problem.** Most needed chunks *are* found by the
   keyword search but rank too low and are cut by the budget or slot limit.
   Recall rises from 0.56 to 0.73 when the package grows 3×.
2. **Reach is a smaller, harder problem.** About 15% of needed chunks are
   still not reached when a quarter of the corpus is handed over (up to 50
   items per kind). Mostly the task's words and the code's words don't
   overlap; some may just rank below 50th.
3. **"Not found" cannot be detected by "zero matches".** In a large corpus
   almost every query matches *something* of every kind, so the two
   missing-information tasks got loosely related results instead of an
   honest "nothing about this".
4. **Bug found:** the token budget counts item text only, so the rendered
   package can exceed `max_tokens` (e.g. ~4.5k against a 4k budget).

Threats: one model family wrote the corpus, tasks and labels (though as
separate agents with separate inputs); 20 tasks is a small sample; labels
reflect one reader's judgement of "needed".
