# Findings: does on-demand context retrieval make coding agents cheaper?

A summary of what this experiment measured, what worked, and what didn't.
Every number here traces back to raw files under
[`benchmarks/results/`](../benchmarks/results/); the detailed log with all
caveats is [`benchmarks/README.md`](../benchmarks/README.md).

## The question

Coding agents need project knowledge: decisions, schemas, conventions, known
bugs, code and tests. There are three obvious ways to supply it:

- **Everything up front.** Put the whole project in the prompt.
- **Let the agent explore.** It searches and reads files itself (what Claude
  Code does by default).
- **Ask a context service.** A shared service retrieves just the relevant
  pieces, with sources and trust labels, when the agent asks.

The hypothesis was that the third option saves tokens without hurting the
work. The experiment was built to test that, not to assume it.

## Setup

- **Project.** "Hallpass", a synthetic council booking system (~140k tokens,
  163 files: code, tests, SQL migrations, ADRs, known issues, meeting notes).
  Four separate agents wrote it from a shared spec, so its wording varies like
  a real team's. Supersede chains, unconfirmed assumptions and outdated docs
  are deliberately included.
- **Tasks.** 20 realistic tickets ("after the clocks went back, Tuesday's
  block booking shows 18:00…"), written by a fifth agent that never saw the
  retrieval system. Each task has hand-labelled "needed" line ranges and a
  grading rubric (3–5 required facts, plus trap rules such as citing a
  superseded decision). Corpus, tasks and rubrics were each committed before
  anything was run against them.
- **Agent.** Claude Code 2.1.292 in `claude -p`, Haiku 4.5, read-only file
  tools, isolated from user settings. The agent writes a short implementation
  plan; plans are graded by the rubric.
- **The service.** SQLite + FTS5 (BM25) with optional local embeddings
  (`nomic-embed-text` via Ollama), exposed to the agent as an MCP tool.

## Result 1: the service saves about a fifth of the cost, if the agent uses it

300 runs (20 tasks × 5 strategies × 3), compared per task with bootstrap 95%
intervals:

| Strategy vs. "agent explores on its own" | Input tokens | Cost (API-equivalent) | Plan quality |
|---|---|---|---|
| **Service, agent told to use it first** | **0.78×** [0.61–0.97] | **0.79×** [0.69–0.89] | no detectable difference |
| Service, merely offered | 0.90× (not significant) | 0.93× | no detectable difference |
| Whole project in the prompt | 5.1× | 2.0× | +0.035 (borderline) |
| Oracle: exactly the labelled pieces | 0.39× | 0.57× | +0.05 (borderline) |

- **Offering a tool isn't enough.** Left to choose, the agent skipped the
  service in 18 of 60 runs.
- **Full context is the expensive way to a small gain.** The ~140k-token
  project is re-sent on every turn. Caching makes that cheaper, not free.
- **There's headroom.** A perfect retriever (the oracle) would save ~60% of
  tokens. The real service gets about a third of that.

## Result 2: retrieval metrics improved; agent behaviour didn't follow

Measured offline against the labels (recall = share of needed pieces returned):

| Retrieval change | Recall (realistic tasks) |
|---|---|
| Keyword search (BM25) | 0.56 |
| + meaning-based search (hybrid) and a follow-up hop | 0.61 |
| + compact excerpts (more pointers per token) | 0.74 |

But in small agent checks:

- **Compact excerpts** didn't lower cost: the agent opened the files behind
  the pointers instead.
- **"Rely on the excerpts" instructions** didn't stop re-reading (31% vs 30%
  of read volume).

**Lesson:** a retrieval metric is not an agent metric. Every pointer the agent
follows costs a file read.

## Result 3: where the tokens actually go

Replaying the 300 recordings showed that most input cost is **old tool
output being re-sent with every later turn**:

- **Reading halved.** With the service, agents opened half as many files as
  when exploring alone (5.4 vs 10.5 per run).
- **Re-reading.** 35% of what they still read was code the service had
  already handed them, mostly re-opened as whole files.
- **The service's own answers** were ~40% of the context re-sent each turn.

Counterfactual estimates from the same recordings (upper bounds, assuming the
agent otherwise behaves the same):

| Policy | Input tokens |
|---|---|
| Service returns whole short files instead of excerpts | +7% to +45% (worse) |
| Service's first answer already includes what the agent later looked for | −5% |
| **Remove each tool result from the context after 3–5 more steps** | **−33% to −53%** |

The last row, editing the context in place, is the idea behind Meta's
*Context Language Models* (agents editing their own working context) and the
Claude API's context-editing feature. It is the largest lever found, and
**it is untested**, because the Claude Code CLI doesn't allow it.

## Result 4: what didn't work

- **A reader sub-agent doing all file reading.** Worse on every task tested:
  1.27× tokens, 1.44× cost, plan score 0.78 vs 0.92. Each sub-agent call
  starts from scratch, and its summaries lose the details the plan needs.
- **Keyword-level tuning** (weak-match filters, reference following, stopword
  changes, term-coverage reranking). Each was flat or worse at a fixed
  budget.
- **Detecting "this doesn't exist" by score.** In a large corpus something
  always matches. Missing information can't be told apart from loosely
  related matches without understanding meaning.

## Result 5: single runs are very noisy

The same task with the same strategy varies about **×1.7 in tokens** from run
to run. Detecting a 50% saving takes ~18 runs; a 20% saving, ~160. Small
checks can only catch large effects. Behaviour measures from traces
(re-reads, tool calls) are far less noisy than token totals.

## Limits

- **One corpus.** It is synthetic, and written by agents from the same model
  family as the one tested.
- **One small model** (Haiku 4.5).
- **Regex-graded plans**, not executed code changes.
- **Small samples.** 20 tasks, and 10-run checks after the main benchmark.
- **Cost is API-equivalent.** Figures are the CLI's list-price estimates, not
  what a subscription is charged.

## What would move this forward

1. **Test in-place context pruning** with an agent loop that can edit its own
   context (Claude API context editing). It is the biggest estimated saving.
   Watch the interaction with prompt caching.
2. **A multi-task benchmark** where agents write verified findings back to the
   service, so later tasks on the same project start ahead. That is what the
   service was designed for, and single-task runs can't show it.
3. **Robustness:** a second model (Sonnet), a real open-source corpus, and an
   independent label and rubric check.
