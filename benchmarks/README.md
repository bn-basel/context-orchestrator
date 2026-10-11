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

## Phase 1c log: improving keyword retrieval (dev set = the 20 Hallpass tasks)

Each change was committed, then measured on both suites from a clean tree.
"Hallpass" numbers are at the default budget (4000 tokens, 3 per kind).

| Step | Change | Hallpass recall / precision | Sample recall | Kept? |
|---|---|---|---|---|
| baseline | (run `…013257Z`) | 0.56 / 0.28 | 0.83 | |
| 1 | Budget covers the rendered package (bug fix) | 0.56 / 0.29 | 0.83 | yes: packages can no longer exceed `max_tokens` |
| 2 | Weak-match filter, `min_relative_score` 0.1–0.5 | 0.56→0.48 / 0.29→0.47 | 0.74→0.45 | off by default |
| 3 | Standard NLTK stopwords | 0.56 / 0.29 | 0.81 | yes (sample only lost T07's lucky "after" match) |
| 4 | Reference following, `max_references` 2–8 (docs only) | 0.56–0.57 / 0.26–0.27 | 0.81 | off by default |
| — | Coordination-factor reranking (exploratory, scratch only, not committed) | 0.47–0.52 | 0.81 | rejected |

What the steps showed:

- **The weak-match filter is a precision dial, not a "nothing exists"
  detector.** Irrelevant matches of the requested kind can score as high as
  relevant ones: a request for an "investigation" matches every finding,
  since every finding is an investigation. Detecting missing information
  needs meaning, not word overlap.
- **Reference following works mechanically but is zero-sum at a fixed
  budget.** On H01 it pulls in exactly the two functions the bug report names
  (both previously missed), but each reference displaces another needed item.
  First version: only 10 of 78 added references were relevant (code-to-code
  calls are noise); restricting it to documents helped precision, not recall.
- **Keyword tweaks have stalled at ~0.56 recall.** The remaining loss is
  ranking quality: relevant chunks are in the candidate pool (recall 0.85 at
  a 32k-token package) but BM25 doesn't put them near the top.
- **The gate has a loophole worth noting:** a huge budget (~32k tokens, 23% of
  the corpus) reaches recall 0.85, passing C1 and C5. That isn't a fix, it's
  handing over a quarter of the haystack; C5's 50% ceiling is too lax for a
  corpus this size. The criteria stay as committed. Phase 2 will price
  package size directly.

Next: meaning-based (semantic) ranking, combined with BM25.

### Phase 1c step 5: meaning-based (hybrid) retrieval

Embeddings: `nomic-embed-text` (Apache-2.0, digest `0a109f422b47`) via a local
Ollama; BM25 and vector ranks fused with reciprocal rank fusion (k=60).
Runs from this step onwards record the model digest in `run.json`.

| Mode | Sample recall / precision | Hallpass recall / precision |
|---|---|---|
| BM25 (current default) | 0.81 / 0.39 | 0.56 / 0.29 |
| Hybrid | **0.94 / 0.41** | 0.57 / 0.30 |
| Semantic only | 0.85 / 0.36 | 0.50 / 0.26 |

Hybrid fixes the vocabulary problem the sample was built to show ("penalty"
finds "fine"), but barely moves Hallpass. Diagnostics on Hallpass:

- **Ceiling.** With perfect ranking at 3 items per kind, recall could reach
  0.92 (7 of 107 labels sit in kinds the task didn't request). So ranking,
  not the slot limit, is the gap.
- **Where the needed chunks rank** within their kind (107 labels):

  | Mode | Top 3 | 4–10 | 11–50 | 51–200 | Not reached |
  |---|---|---|---|---|---|
  | BM25 | 59 | 19 | 13 | 7 | 9 |
  | Hybrid | 60 | 21 | 12 | 1 | 13 |

  Embeddings reshuffle the order but don't bring many more needed chunks into
  the top 3.
- **Why.** Many needed chunks are relevant by *reasoning*, not by topic: the
  transaction helper a race-condition fix will need, the migration that adds a
  column, the test fixture that a new test must use. An engineer reaches them
  in steps (ticket → function → what it calls). A single query, whether by
  words or by meaning, does not.

Conclusion so far: **single-shot retrieval looks capped well below gate 1's
0.80 on realistic tasks.** Gate 1 measures one request per task; strategy B
in phase 2 lets the agent make several requests and read files itself, which
is the multi-step search these misses need. Whether that is enough is exactly
what phase 2 measures.

### Phase 1c step 6: two-step retrieval (search, then search for what the top results name)

| Config | Sample recall / precision | Hallpass recall / precision |
|---|---|---|
| BM25, 1 hop (baseline) | 0.81 / 0.39 | 0.56 / 0.29 |
| BM25, 2 hops, follow-up fused into every kind | 0.81 / 0.39 | 0.53 / 0.28 |
| BM25, 2 hops, follow-up for code/test/schema only | 0.81 / 0.39 | 0.55 / 0.30 |
| Hybrid, 1 hop | 0.94 / 0.41 | 0.57 / 0.30 |
| **Hybrid, 2 hops (code/test/schema)** | **0.94 / 0.41** | **0.61 / 0.32** |

Why two hops barely help with BM25: the follow-up searches for names found in
the first search's top 4 results, and only 54% of those seeds are relevant
(top-1 relevant in 16 of 20 tasks). Half the names come from the wrong chunks
and the search drifts ("query drift", the classic failure of pseudo-relevance
feedback). With hybrid ranking the seeds are better and the follow-up gains a
little. Exploratory scratch runs (not committed) with the follow-up at half
weight gave 0.54–0.56: no better.

## Phase 1c conclusion

Best single-request configuration on the development set: **hybrid + 2 hops,
recall 0.61, precision 0.32** at ~3k tokens (2% of the corpus). Gate 1 needs
0.80. Twenty tasks are a small sample; differences of a few hundredths are
within noise.

What was learned:

1. **Vocabulary mismatch is solvable** with embeddings (sample: 0.81 → 0.94).
2. **Realistic coding tasks need reasoning-driven hops.** The missing pieces
   (the helper a fix will call, the migration that adds a column) are linked to
   the task by an engineer's reasoning, not by words or topic, and automatic
   follow-ups drift when the first results are only half right.
3. **Gate 1, as defined (one request per task), is not passed** by any method
   tried. Phase 2's strategy B gives an agent the service as a tool it can call
   repeatedly, with its own judgement choosing the next request: the missing
   ingredient here. Whether that closes the gap is phase 2's question.

## Phase 2 pilot: agent comparison (run `20261011T030237Z-hallpass-agent`)

Claude Code 2.1.292, model Haiku 4.5 (`--model haiku`), 4 tasks (H01 bug fix,
H12 cross-area, H15 superseded trap, H17 assumption trap) × 4 strategies × 1
run. Identical prompt and read-only file tools (Read, Grep, Glob) for every
strategy; B adds the `request_context` MCP tool (hybrid + 2 hops). Plans are
graded by the regex rubrics in `tasks/hallpass.rubrics.json`, which were
committed before the run. Raw streams were re-sanitised after the run (the OS
user name appeared inside Claude Code's own folder names); the sanitiser now
handles that.

| Strategy | Mean score | Successes | Traps hit | Median input tokens (cache read share) | Median output | Median duration | API-equiv. cost, 4 runs |
|---|---|---|---|---|---|---|---|
| A full context | 0.80 | 1/4 | 1 | 1,605k (93%) | 3.4k | 55 s | $1.10 |
| B context service | 0.90 | 2/4 | 0 | 236k (88%) | 4.8k | 58 s | $0.45 |
| C file tools only | 0.70 | 1/4 | 0 | 366k (92%) | 4.5k | 77 s | $0.49 |
| D oracle ranges | 0.75 | 1/4 | 0 | 164k (90%) | 3.7k | 47 s | $0.31 |

Tokens and durations are measured by Claude Code; cost is its API-list-price
estimate, **not** a subscription charge. Total: about $2.35 API-equivalent.

**This pilot tests the pipeline. It does not answer the question.** One run
per cell and four tasks are far too few, and the score differences are
within noise. What it did show:

1. **The pipeline works end to end:** isolation, MCP, stream parsing, usage,
   grading and raw storage. All 16 runs completed.
2. **B mostly didn't use the service.** The agent called `request_context`
   in only 2 of 4 runs (once in H12, twice in H17). In H01 and H15 it explored
   files exactly like C. B's scores can't be credited to the service yet.
3. **Full context is expensive even with caching.** A's agents still made
   5–17 file-tool calls, and every turn re-sent the ~140k-token corpus: a
   median of 1.6M input tokens per run, 93% of them cache reads. That is 4–7×
   the other strategies, and 2.5× the API-equivalent cost of B or C.
4. **The oracle isn't a ceiling for plan quality.** D received exactly the
   labelled ranges but scored below B. Knowing the facts is not the same as
   writing them into the plan, and the regex rubric misses some paraphrases.

## Phase 2 result: agent comparison (run `20261011T032628Z-hallpass-agent`)

Claude Code 2.1.292, Haiku 4.5, commit `236e659` (clean). 20 Hallpass tasks ×
5 strategies × 3 repetitions = 300 runs, 4 in parallel, order shuffled (seed
20261011); 67 minutes; **0 failed runs**. About **$31 API-equivalent** in
total (the CLI's list-price estimate, not a subscription charge). Raw event
streams are stored gzip-compressed (`raw/*.jsonl.gz`); the analysis below
comes from `runs.jsonl` alone (`ctxo analyze-agent <run folder>`).

Strategies: **A** whole corpus (~140k tokens) appended to the system prompt;
**B** context service offered as an MCP tool (hybrid retrieval, 2 hops);
**B2** the same, plus "start by calling request_context"; **C** no extra
context, file tools only; **D** oracle: only the hand-labelled ranges. All
have the same prompt and the same read-only file tools.

| Strategy | Mean score | Fully correct plans | Traps hit | Median input tokens | Median duration | API-equiv. cost (60 runs) |
|---|---|---|---|---|---|---|
| A whole corpus | 0.84 | 27/60 | 1 | 1,508k | 48 s | $11.63 |
| B service offered | 0.80 | 22/60 | 1 | 251k | 55 s | $5.49 |
| B2 service, use it first | 0.79 | 20/60 | 0 | 193k | 47 s | $4.62 |
| C file tools only | 0.81 | 19/60 | 2 | 270k | 56 s | $5.77 |
| D oracle | 0.86 | 28/60 | 0 | 125k | 40 s | $3.50 |

**Paired comparisons** (per task, 95% bootstrap intervals over the 20 tasks;
full table in the run's `analysis.md`):

| Comparison | Score difference | Input tokens | Cost |
|---|---|---|---|
| B2 vs C | −0.017 [−0.060, +0.026] | **0.78× [0.61, 0.97]** | **0.79× [0.69, 0.89]** |
| B vs C | −0.008 [−0.081, +0.060] | 0.90× [0.70, 1.12] | 0.93× [0.81, 1.05] |
| A vs C | +0.035 [−0.015, +0.080] | 5.12× [4.00, 6.35] | 1.97× [1.59, 2.32] |
| D vs C | +0.048 [−0.012, +0.111] | 0.39× [0.28, 0.52] | 0.57× [0.47, 0.67] |
| B2 vs A | −0.052 [−0.094, −0.009] | 0.15× [0.12, 0.20] | 0.40× [0.33, 0.50] |

Service use: B called the tool in 42 of 60 runs (1.08 calls on average), B2 in
59 of 60 (1.87). B2 needed fewer file-tool calls than C (median 12 vs 17).

### What this shows (and what it doesn't)

1. **Told to use it, the context service saves about a fifth of the cost
   against unaided exploration** (B2 vs C: 0.79× cost, interval excludes
   1.0), **with no detectable loss in plan quality.** "No detectable loss" is
   not "equal": the score interval spans −0.06 to +0.03.
2. **Merely offering the tool is not enough.** Offered (B), the agent skipped
   it in 18 of 60 runs, and the savings fall within noise.
3. **Full context is the most expensive way to get a small quality edge.** A
   used 5× the input tokens of C and twice the cost (cache reads soften
   but don't remove the re-sending of 140k tokens every turn). Its quality
   lead over C is borderline; over B2 it is small but detectable (+0.05).
4. **Perfect retrieval would save much more.** The oracle uses 0.39× C's
   tokens. The service gets part of the way, consistent with its ~0.6 recall
   in phase 1. Better retrieval is where the remaining savings are.

Threats to validity: one synthetic corpus written by agents of the same model
family; one small model (Haiku 4.5); plans graded by regex rubrics (fast and
transparent, but blind to some paraphrases and lenient on some checks);
20 tasks; 8 comparisons × 4 measures without multiple-comparison correction,
so a single borderline interval (e.g. B2 vs A on score) may be chance. The
model may also have prior knowledge of common patterns, though not of this
fictional project.

## Phase 3a: compact packages (retrieval only, no model calls)

Idea: items show only their opening lines (code: signature and docstring;
docs: first lines of the section) plus the exact location, so a package can
point at more of the right places; the agent reads the rest with its file
tools. Measured with `--detail compact` on the same tasks (Ollama for hybrid):

| Suite, retrieval (2 hops) | Full text, 3 per kind | Compact, 3 per kind | Compact, 8 per kind |
|---|---|---|---|
| Hallpass, hybrid | 0.61 recall / 0.32 precision, ~3.1k tokens | 0.61 / 0.31, **~1.3k tokens** | **0.74** / 0.15, ~3.1k tokens |
| Hallpass, BM25 | 0.55 / 0.30, ~3.0k | | 0.70 / 0.14, ~3.1k |
| Sample, hybrid | 0.94 / 0.41, ~0.6k | | 1.00 / 0.20, ~1.3k |

At the same size, compact packages reach 0.74 recall instead of 0.61; or the
same recall with 60% fewer tokens. Caveat: recall here means the package
*points at* the needed range and shows its opening, not its full text.
Whether that helps an agent needs an agent check (planned small: ~10 runs).

### Phase 3a agent check: compact vs full packages (run `20261011T053311Z-hallpass-agent`)

Small by design (owner's rule: start with ~10 runs, scale only on a signal).
Haiku 4.5, 5 tasks chosen before the run (H01, H06, H11, H13, H15: one per
task type) × B2 (full packages) and B2C (compact packages, 8 per kind) × 1
run. $0.81 API-equivalent in total.

| | B2 full | B2C compact |
|---|---|---|
| Mean score | 0.88 | 0.84 |
| API-equivalent cost (5 runs) | $0.40 | $0.42 |
| Median input tokens | 224k | 291k |
| Service calls per run | 3, 3, 1, 3, 4 | 2, 1, 1, 1, 1 |
| File-tool calls per run | 8, 15, 6, 9, 12 | 20, 4, 13, 17, 18 |

**No signal, so not scaled up.** With full packages the agent asked the
service follow-up questions and read fewer files; with excerpts it mostly
asked once and then opened the files itself, which costs about the same. The
higher recall of compact packages is "points at the right place", and the
agent pays to follow each pointer. Full packages stay the default; compact
mode remains available (`--detail compact`).

## Phase 3b: what agents actually read (no model calls)

`ctxo analyze-traces` re-reads the 300 raw streams of the phase 2 run and
classifies every file read against (1) what the context service had returned
*before* that read and (2) the task's labelled ranges. Output:
`results/20261011T032628Z-hallpass-agent/traces.md` and `traces.json`.
"Carried" context weights each tool result by the number of later tool calls,
because it is re-sent with each: a proxy for input-token cost.

| | B2 (service, used first) | B (offered) | C (file tools only) |
|---|---|---|---|
| File reads per run | **5.4** | 8.9 | 10.5 |
| Characters read per run | **22.6k** | 36.2k | 44.6k |
| Read volume: already served by the service | **35%** | 8% | n/a |
| Read volume: needed, not served (recovering misses) | 25% | 42% | 45% (needed) |
| Read volume: unrelated | 38% | 50% | 55% |
| Carried context: file reads / service answers | 50% / **39%** | 68% / 15% | 83% / n/a |
| Labelled ranges: served / read only / never seen | 33% / 30% / 37% | 18% / 55% / 27% | 0% / 72% / 28% |

Mean score by how many labelled ranges the agent never saw (0 / 1 / 2+):
B 0.91 / 0.84 / 0.72; B2 0.90 / 0.80 / 0.78; C 0.83 / 0.85 / 0.76.

What this says about B2's cost:

1. **The saving is real reading avoided.** B2 agents open half as many files
   as C and read half as much text.
2. **A third of what B2 still reads, it already had.** 35% of its read volume
   re-opens ranges the service had returned, 70% of the time as a whole-file
   read, spread across the run. The agent takes the excerpt, then opens the
   whole file around it later.
3. **The service's answers are a large share of the cost.** 39% of B2's
   carried context is package text, re-sent on every later turn. Package
   text and later file reads overlap.
4. **Missing pieces still cost quality.** Runs that never saw 2+ needed ranges
   score lower in every strategy, so recall matters for quality as well.

Caveats: "served" means the read overlaps a returned range; a whole-file read
counts even if the agent wanted another part of the file. Labels are one
annotator's view of "needed". Coverage is n/a for A and D, which received
their context in the prompt.

Implications for the next change (to test with ~10 runs): tell the agent the
excerpts are verbatim with exact line ranges, so it opens files only for
parts not shown; and/or shrink packages, since they are re-sent every turn.

### Phase 3b agent check: "rely on the excerpts" (run `20261011T054511Z-hallpass-agent`)

Haiku 4.5, same 5 tasks as phase 3a × B2 and B2V (B2 + "Its excerpts are
verbatim with exact file paths and line ranges: rely on them, and open a file
only for parts that were not shown") × 1 run. $0.75 API-equivalent.

| | B2 | B2V |
|---|---|---|
| Mean score | 0.92 | 0.84 |
| API-equivalent cost (5 runs) | $0.385 | $0.369 |
| File reads per run | 5.4 | 4.4 |
| Read volume re-opening served ranges | 30% | 31% |

**No signal; not scaled up.** The instruction did not reduce re-reading of
served ranges (30% vs 31%).

**How noisy are single runs?** Across the 300 phase 2 runs, the same task and
strategy vary in input tokens by a standard deviation of 0.50 in log terms
(about ×1.7 either way). With per-task pairing, detecting a 50% token saving
at 80% power needs ~18 runs, and a 20% saving ~160 runs. Small (~10-run)
checks can catch large effects and clear behaviour changes, not modest
savings. Cheaper, less noisy signals (behaviour measures from traces, such as
re-read share or service-call counts) are better targets for small checks.

## Phase 3c: what-if estimates from the recordings (no model calls)

`ctxo what-if <run> --suite <suite>` replays the 300 phase 2 recordings under
alternative policies and estimates the change in input tokens. Results in
`results/20261011T032628Z-hallpass-agent/what_if.md`.

**Cost model.** Per strategy, input tokens ≈ a × model calls + b × carried
characters (tool output re-sent on every later call). Fits are good
(correlation of log predicted vs log actual 0.85–0.96; b ≈ 0.2–0.55 tokens per
character). For A the fixed ~120k-token prompt dominates and no usable b
exists, so A is excluded.

| Policy | B | B2 | C | D |
|---|---|---|---|---|
| Service returns whole files ≤ 4k chars | +7% | +20% | n/a | n/a |
| Service returns whole files ≤ 8k chars | +18% | +45% | n/a | n/a |
| First answer already holds what the agent later went to find | −4% | −5% | n/a | n/a |
| Prune each tool result after 10 more calls | −19% | −13% | −16% | −3% |
| Prune each tool result after 5 more calls | −45% | −33% | −40% | −10% |
| Prune each tool result after 3 more calls | −59% | −48% | −53% | −15% |

Mean change per run (medians in `what_if.md`), **assuming the agent otherwise
behaves the same**. That is an upper bound: phase 3a showed agents react to
what they receive.

What this says:

1. **Returning whole files would make things worse.** The extra text is
   re-sent every turn, which outweighs the re-reads it saves.
2. **Better first answers save little directly** (≈5%). Retrieval quality
   matters more for plan quality than for tokens.
3. **In-place pruning of old tool output is by far the largest lever**:
   about a third to a half of input tokens with a 3–5 call window. This is
   the idea behind Meta's Context Language Models (agents editing their own
   context) and the Claude API's context editing (`clear_tool_uses`).
   Two caveats: tokens are not cost (prompt caching makes re-sent context
   cheap, ~0.1× price, and any edit invalidates the cache after the edit
   point, so frequent pruning trades cheap cache reads for cache writes); and
   pruning cannot be applied inside the Claude Code CLI used for these runs.
   Testing it needs our own agent loop.
