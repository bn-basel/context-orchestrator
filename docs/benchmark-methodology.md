# Benchmark methodology

Status: both stages have run (phase 1 retrieval-only, phase 2 agent
comparison); results in [benchmarks/README.md](../benchmarks/README.md).
Deviations from the original design are listed under "As run" below. This document fixes the method
before results exist, so the results cannot shape the method.

## Stage 1: retrieval-only evaluation (implemented)

Before spending model calls, retrieval is scored on its own against
hand-labelled tasks: recall and precision over labelled line ranges, rank
of the first relevant item, superseded items returned, missing kinds
reported, and assumption labels preserved. Labels and gate criteria
([benchmarks/gate1.json](../benchmarks/gate1.json)) are committed before
the evaluator runs. Results and caveats: [benchmarks/README.md](../benchmarks/README.md).

The rest of this document describes stage 2, the agent comparison.

## Question

For a coding agent working on a project, does on-demand context retrieval
reduce token usage and cost **without lowering task success**, compared with
giving the agent the full relevant context up front? And what does the
retrieval itself cost (extra turns, tool calls, latency)?

Either answer is useful. Retrieval could easily cost *more* overall, through
extra round trips, repeated system prompts and missed context that causes
rework. The benchmark must be able to show that.

## Strategies

| ID | Name | What the agent gets |
|---|---|---|
| A | Full-context baseline | Task + a fixed context package containing the whole benchmark corpus, rendered as Markdown in the prompt |
| B | On-demand retrieval | Task + access to the `ctxo request` tool for the same corpus; no context up front |
| C (control) | No context | Task only; the agent may read files with its normal tools |
| D (reference) | Oracle context | Task + only the hand-labelled relevant chunks; an upper bound for retrieval quality |

A vs. B is the main comparison. C and D bracket it: if B is no better than C,
the service adds nothing; the gap between B and D measures retrieval loss.

## Held constant

Model and model version, task prompt template (byte-identical apart from the
strategy-specific block), available tools (B adds exactly one), turn limit,
working copy of the project (fresh copy per run), and the evaluation script.
The only variable is how context is supplied.

### Isolating Claude Code runs

Checked against Claude Code 2.1.292 on 2026-10-11:

- `claude -p --output-format json` reports, per model: `inputTokens`,
  `outputTokens`, `cacheReadInputTokens`, `cacheCreationInputTokens`,
  `thinkingTokens`, `costUSD` with `costBasis: "list"`, and run-level
  `duration_ms`, `duration_api_ms`, `num_turns`, `is_error`.
- `--bare` would give the cleanest isolation (no hooks, plugins, auto-memory
  or CLAUDE.md discovery), but it authenticates **only** with
  `ANTHROPIC_API_KEY`. It cannot be used with a subscription login.
- On a subscription, isolate with: a scratch working directory outside any
  folder containing a `CLAUDE.md`, `--setting-sources project`,
  `--strict-mcp-config --mcp-config <benchmark config>`, `--tools <fixed
  list>`, `--disable-slash-commands`, `--no-session-persistence`, and a fixed
  `--model`. Still **to verify** before the first run: whether user-level
  `~/.claude/CLAUDE.md` and auto-memory are excluded under these flags. If
  they cannot be excluded, they are a constant across strategies and must be
  documented as such.
- A one-word `claude -p` reply measured about 35k input tokens (mostly cache
  reads) of harness overhead. That overhead is part of every run and of every
  extra turn in strategy B, so it must be reported, not subtracted.

## Tasks and corpus

- Tasks are written against a fixture project (starting with
  `examples/sample_project`, then larger synthetic projects). Each task has
  an objective check: a hidden test suite that must pass, plus a list of
  facts the solution must respect (for example "fines are integer cents").
- Each task has a hand-labelled set of **relevant chunks** (by file and line
  range), written before any run, for retrieval precision and recall.
- Task mix: bug fixes with a documented known issue, features constrained by
  an ADR, schema-dependent changes, and tasks whose key fact is an
  *assumption* or a *superseded* decision (traps for stale context).

## Metrics

| Metric | Source | Kind |
|---|---|---|
| Input tokens (uncached, cache read, cache write) | `modelUsage` in CLI JSON | measured (provider-reported) |
| Output and thinking tokens | `modelUsage` | measured (provider-reported) |
| Turns, tool calls, `ctxo` calls | CLI JSON / stream-json events | measured |
| Wall-clock and API latency | CLI JSON `duration_ms`, `duration_api_ms` | measured |
| Retrieval latency | `ctxo` telemetry `latency_ms` | measured |
| Package size in the service | `ctxo` telemetry `package_tokens` | estimated (chars / 4) |
| API-equivalent cost | CLI `costUSD` (`costBasis: list`) | estimated |
| Recomputed cost | tokens × documented price table | estimated |
| Task success | hidden tests pass (yes/no) + fact checks | measured |
| Retrieval precision / recall | returned chunks vs. labelled relevant chunks | measured |
| Retrieval failures | relevant chunks never returned; `unresolved` entries | measured |

Rules:

- A missing field is recorded as **unavailable** and excluded from that
  aggregate, with the count of exclusions reported. It is never zero.
- **Subscription usage and API-equivalent cost are reported separately.** A
  subscription has no exact per-call price. `costUSD` is the CLI's list-price
  equivalent, and is labelled as such. A recomputed cost uses a versioned
  price table committed to the repository with its source and date.
- Token totals are reported per component (uncached / cache read / cache
  write / output), because cache reads are priced very differently.

## Protocol

1. Freeze the task set, labels, price table and harness version, and commit them.
2. For each task × strategy, run *N* ≥ 5 repetitions. Interleave the run
   order randomly with a recorded seed.
3. Give each run a fresh project copy, a fresh session (`--no-session-persistence`),
   and the same flags.
4. Store raw outputs unmodified as JSONL under `benchmarks/results/<run-id>/`:
   CLI result JSON, stream events, `ctxo` telemetry, test results, and the
   exact command line. Analysis reads only these files.
5. Report per-task medians and spreads, not just means, along with
   success-conditional token usage. Success differences of a few tasks on a
   small set are noise and are labelled as such.

## Threats to validity

- Small, synthetic corpora favour retrieval less than real repositories, or
  more; results do not generalise beyond the corpora used.
- Prompt caching makes strategy A's repeated context cheap after the first
  turn; ignoring cache reads would overstate its cost.
- Agents in strategy B may ignore the tool. Tool-call counts are reported.
- The harness's own context (system prompt, tool definitions) dominates small
  tasks and narrows any difference.
- One model family; results may differ for others.

## As run (phase 2)

- **Success measure.** The Hallpass corpus is written to be read, not executed
  (no database), so hidden test suites were replaced by **implementation plans
  graded with per-task regex rubrics**: 3–5 required facts per task plus trap
  rules (e.g. citing a superseded decision). Rubrics were written by the agent
  that wrote the tasks, self-checked against example good and bad plans, and
  committed before any run.
- **Strategies.** A, C and D as designed; B split into **B** (tool offered) and
  **B2** (told to call it first), because in the pilot the agent ignored the
  offered tool in half the runs.
- **Isolation.** `claude -p` with `--tools Read,Grep,Glob`, `--strict-mcp-config`,
  `--setting-sources project`, `--disable-slash-commands`,
  `--no-session-persistence`, `--exclude-dynamic-system-prompt-sections`, a
  scratch workspace outside any folder with a CLAUDE.md. The start-up event
  confirmed exactly the intended tools and no skills. There is no user-level
  `~/.claude/CLAUDE.md` on the test machine; auto-memory cannot be written
  with read-only tools.
- **Analysis.** Per-task paired differences (scores) and geometric-mean ratios
  (tokens, cost) with 95% bootstrap intervals over tasks, computed from
  `runs.jsonl` alone. No multiple-comparison correction.
