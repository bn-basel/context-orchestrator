# Context Orchestrator

An experiment in making AI coding agents cheaper without making them worse:
a small context service for agents, a benchmark harness, and every raw
result from 460 graded agent runs.

## Key result

> **Making a coding agent ask a context service before it reads files cut
> its token use by about half (−49%) and its cost by 36%, with no loss in
> quality.** It was cheaper in 29 of 30 paired runs.

Stacking more levers on top saves more, but costs quality. Each row below is
compared with a plain agent that explores the files itself:

| Setup | Tokens | Cost | Plan quality |
|---|---|---|---|
| **Ask the context service first** | **−49%** | **−36%** | **same** (−0.02) |
| … and think less (low effort) | −74% | −62% | slightly lower (−0.05, just past our bar) |
| … and think less and trust reviewed memory | −83% | −72% | lower (−0.15): it stopped opening files |

**How to apply it:**
- **Give the agent a context tool.** This repository's MCP server works;
  see *Try it*.
- **Make it the first step:** tell the agent to call the tool before reading
  any files. Merely offering the tool saved nothing clear, because agents
  often skipped it.
- **Add low effort** only where a slightly less thorough answer is
  acceptable.

Measured on one project with small models; details below. Tokens are input
tokens.

## TL;DR

- **Problem:** coding agents spend most of their budget reading and
  re-reading project context.
- **What we did:**
  - Built a context service and tested a dozen ideas and combinations for
    cutting that cost.
  - Each was compared with the same agent without the idea, on 20 realistic
    tasks with answers graded by fixed rubrics: 565 runs in all.
  - Every test was planned before it ran.
- **What worked:**
  - **Asking a context service first:** about half the tokens, 36% cheaper,
    same quality. This is the most robust result.
  - **Thinking less:** 29% cheaper on its own, same quality. On top of the
    service it saves more but starts to cost quality.
- **What didn't:**
  - **The whole project in the prompt:** doubled the cost.
  - **Pruning old context as the agent works,** the idea behind Meta's
    *Context Language Models*: looked like a 33–53% saving on paper, cost
    more in practice.
  - **Memory of earlier tasks:** saved nothing unreviewed, because agents
    re-checked every finding. Reviewed and trusted, it saved 18% over an
    agent told to double-check, but nothing on top of the service.
  - **All the levers at once:** 72% cheaper, but the agent stopped reading
    files and its answers got worse.
- **The lessons:**
  - **Agents don't trust what they're handed,** so they read it again.
    Making the context service the first step is what turns good context
    into savings.
  - **Savings don't simply add up:** past a point, a cheaper agent is a
    shallower one.
  - **Measure, don't extrapolate.**

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/results-dark.svg">
  <img alt="Bar chart of the change in cost for each idea against the same agent without it. Works with the same quality: ask a context service first (-21% in the first study, -36% against a plain agent in the second) and think less (-29%); reviewed memory -18% (slightly less thorough). No clear saving: offering the service, outline-first reads, unreviewed memory, pruning (+17%). The whole project in the prompt costs +97%. Combinations: service first and think less -62% (quality just under the bar); all three -72% (lower quality)" src="docs/img/results-light.svg">
</picture>

## What we tested

- **A realistic project:** a fictional council booking system, about 140k
  tokens of code, tests, database migrations, design decisions and known
  bugs. Outdated and contradictory documents are mixed in on purpose.
- **20 tasks** like real tickets, each graded against a rubric written
  before any run.
- **Ways of giving the agent context:**
  - the whole project in the prompt;
  - letting it explore alone;
  - our context service, offered or required first;
  - an ideal "exactly the right pieces" baseline.
- **Ways of changing how the agent works:**
  - pruning old context as it goes;
  - showing long files as an outline first;
  - thinking less;
  - memory of earlier tasks, unreviewed and reviewed.
- **Combinations** of the levers that worked, against a plain agent.
- **Setup:**
  - 300 runs in Claude Code with Claude Haiku 4.5;
  - 265 runs in a small agent loop of our own with Claude Haiku 5.5, $1.42
    actually charged.
  - Every comparison is paired by task with 95% intervals.

## What we found

- **Asking a context service first is the strongest result:**
  - In the first study it saved 21%.
  - In our own loop it saved 36% of cost and 49% of tokens, measured
    against a plain agent over 30 pairs.
  - Quality didn't change in either case.
  - Merely offering the service saved nothing clear: agents skipped it in
    18 of 60 runs.
- **Thinking less saved 29%** with no change in quality. The agent thought
  about two-thirds less and also took fewer, smaller steps. All 10 pairs
  were cheaper.
- **Reviewed memory saved 18% against an agent told to double-check
  findings, but nothing on top of the service.**
  - Findings from earlier tasks were checked against the code and served as
    verified, and agents were told they could rely on them.
  - They then re-opened 35% of the files the findings cited, instead of 59%.
  - Against an agent that simply asks the service first, the extra saving
    vanished (×0.98): the service already supplies most of what the findings
    say.
  - The review was done by Claude, not by a person.
- **Unreviewed memory saved nothing.** The findings were accurate and
  reached the agent, but it checked them by opening the files anyway.
- **The whole project in the prompt doubled the cost**, because it is sent
  again on every step.
- **Pruning old context didn't pay** (+17%, not significant). Replays of the
  first runs predicted a 33–53% saving. On the newer model the agent works
  in a few wide steps, so little old context is re-sent. It went back for
  what was removed, and each edit made part of the cache be written again.
- **Combining levers saves more, but at a cost.**
  - Service first plus thinking less saved 62% of cost (74% of tokens), but
    its quality drop just crossed our bar (−0.05).
  - Adding trusted memory as well saved 72%, but the agent stopped opening
    files and missed details nobody had handed it (score −0.15).
- **Outline-first reads were inconclusive** (−9%): the agent rarely reads
  long files whole anyway.
- **A helper agent doing all the reading was worse:** more cost, lower
  quality. Its summaries lose the details the plan needs.
- **Single runs are noisy** (token use varies by about 1.7× between runs of
  the same task), so small tests only catch large effects.

## What we think

- **Make asking for context the agent's first step.** It is the one change
  that saved a lot without hurting answers, in both setups. Offering it
  isn't enough.
- **Trust is the bottleneck, not retrieval.** Agents verify what they're
  given by reading the source again. Accurate memory only saves money once
  the agent may rely on it, and then it overlaps with what the service
  already provides.
- **Cheaper stops being better at some point.** Each lever on its own kept
  quality. Stacked, they pushed the agent from checking less to not
  looking at all.
- **Look at where the money goes first, and measure.** For the newer model,
  46% of cost was storing newly read context, 38% output, 16% re-sending
  old context. Pruning could only touch the 16%. The biggest saving on
  paper vanished when the model changed.
- **The evidence is narrow:**
  - one synthetic project and two small models;
  - graded plans rather than executed code;
  - small samples for the later tests.

  Treat the numbers as careful first measurements, not general laws.

The full write-up is in [docs/findings.md](docs/findings.md); every run with
its caveats is in [benchmarks/README.md](benchmarks/README.md).

## Try it

Python 3.11+, no runtime dependencies. Optional meaning-based search uses a
local [Ollama](https://ollama.com) with `nomic-embed-text`.

```bash
git clone https://github.com/bn-basel/context-orchestrator.git
cd context-orchestrator
uv sync
uv run ctxo ingest examples/sample_project
uv run ctxo request examples/sample_project --task "Why are fines capped?" --kind decision --kind code --format markdown
```

To use it from Claude Code, run it as an MCP tool:

```json
{"mcpServers": {"ctxo": {"command": "uv", "args": ["run", "--directory", "path/to/context-orchestrator", "ctxo", "mcp", "path/to/project"]}}}
```

Every answer contains verbatim excerpts with file paths and line ranges,
trust labels (verified, observed, assumption), and a list of what it could
not find.

## Reproduce

```bash
uv run pytest
uv run ctxo eval-retrieval benchmarks/tasks/hallpass.json
uv run ctxo eval-agent benchmarks/tasks/hallpass.json --rubrics benchmarks/tasks/hallpass.rubrics.json --tasks H01 --strategies B2,C --service-args "--retrieval bm25 --hops 2"
uv run ctxo analyze-agent benchmarks/results/<run>
uv sync --group loop
uv run ctxo loop-eval prune benchmarks/tasks/hallpass.json --rubrics benchmarks/tasks/hallpass.rubrics.json --arms L,LP --tasks H17,H13,H11,H19,H09
uv run python benchmarks/memory_analysis.py benchmarks/results/<memory-run>
uv run python benchmarks/charts/results_chart.py
```

`eval-retrieval` makes no model calls. `eval-agent` runs Claude Code and uses
real usage, so start small. The published Claude Code runs used
`--model haiku` (then Haiku 4.5) and `--retrieval hybrid` (needs Ollama);
`bm25` works without it. `loop-eval` calls Claude Haiku 5.5 through
OpenRouter with the key in a git-ignored `.env` (see `.env.example`), stops
itself at an estimated $2, and records OpenRouter's charge per call. Method:
[docs/benchmark-methodology.md](docs/benchmark-methodology.md). Design:
[docs/architecture.md](docs/architecture.md). Plans: [ROADMAP.md](ROADMAP.md).

## License

[MIT](LICENSE).
