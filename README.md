# Context Orchestrator

An experiment in making AI coding agents cheaper without making them worse:
a small context service for agents, a benchmark harness, and every raw
result from 460 graded agent runs.

## Key result

> **Turning the model's thinking effort down from medium to low cut token use
> by a third (−33%) and cost by 29%, with no loss in quality.** It was cheaper
> in every one of the 10 paired runs.

Three changes cut cost in our tests:

| Change | Tokens | Cost | Quality | How to apply it |
|---|---|---|---|---|
| **Lower the thinking effort** | **−33%** | **−29%** | same | Set effort to `low`: `output_config.effort` in the Claude API, `--effort low` in Claude Code |
| **Make the agent ask for context first** | −22% | −21% | same | Give it a context tool (like this repo's) and tell it to call it before reading files. Offering the tool alone didn't help |
| **Let agents trust reviewed memory** | −22% | −18% | slightly less thorough | Save findings anchored to file lines, review them, and tell agents reviewed findings need no re-checking |

Each change was measured separately against the same agent without it, on
one project with small models (details below). They were **not tested
together**, so don't add the percentages up. Token figures are input tokens
(for effort, output tokens fell by 33% too).

## TL;DR

- **Problem:** coding agents spend most of their budget reading and
  re-reading project context.
- **What we did:** built a context service and tested nine ideas for cutting
  that cost, each against the same agent without the idea, on 20 realistic
  tasks with answers graded by fixed rubrics. Every test was planned before
  it ran.
- **What worked:**
  - **Asking a context service first:** 21% cheaper, same quality. Only when
    the agent was told to ask: when the service was merely offered, agents
    often skipped it.
  - **Thinking less** (the model's low-effort setting): 29% cheaper, same
    quality.
  - **Reviewed memory from earlier tasks**, which agents were told they could
    trust: 18% cheaper, slightly less thorough.
- **What didn't:**
  - **The whole project in the prompt:** doubled the cost.
  - **Pruning old context as the agent works,** the idea behind Meta's
    *Context Language Models*: looked like a 33–53% saving on paper, cost
    more in practice.
  - **Unreviewed memory:** saved nothing, because agents re-checked every
    finding.
- **The lessons:**
  - **Agents don't trust what they're handed,** so they read it again.
    Trust, not retrieval, is the bottleneck.
  - **Look at where the money goes before optimising.**
  - **Measure, don't extrapolate.**

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/results-dark.svg">
  <img alt="Bar chart of the change in cost for nine ideas, each against the same agent without it. Worked: ask a context service first (-21%), think less (-29%), reviewed memory (-18%). Did not: offering the service (-7%, no clear saving), the whole project in the prompt (+97%), outline-first reads (-9%, inconclusive), unreviewed memory (-2%), pruning (+17%). Best case, handing over exactly the right pieces: -43%." src="docs/img/results-light.svg">
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
- **Setup:**
  - 300 runs in Claude Code with Claude Haiku 4.5;
  - 160 runs in a small agent loop of our own with Claude Haiku 5.5, $0.91
    actually charged.
  - Every comparison is paired by task with 95% intervals.

## What we found

- **Asking a context service first saved 21%** with no change in quality.
  Merely offering the service saved nothing clear: agents skipped it in 18
  of 60 runs.
- **Thinking less saved 29%** with no change in quality. The agent thought
  about two-thirds less and also took fewer, smaller steps. All 10 pairs
  were cheaper.
- **Reviewed memory saved 18%.** Findings from earlier tasks were checked
  against the code and served as verified, and agents were told they could
  rely on them. They then re-opened 35% of the files the findings cited,
  instead of 59%. They missed slightly more rubric points, within the margin
  set in advance. The review was done by Claude, not by a person.
- **Unreviewed memory saved nothing.** The findings were accurate and
  reached the agent, but it checked them by opening the files anyway.
- **The whole project in the prompt doubled the cost**, because it is sent
  again on every step.
- **Pruning old context didn't pay** (+17%, not significant). Replays of the
  first runs predicted a 33–53% saving. On the newer model the agent works
  in a few wide steps, so little old context is re-sent. It went back for
  what was removed, and each edit made part of the cache be written again.
- **Outline-first reads were inconclusive** (−9%): the agent rarely reads
  long files whole anyway.
- **A helper agent doing all the reading was worse:** more cost, lower
  quality. Its summaries lose the details the plan needs.
- **Single runs are noisy** (token use varies by about 1.7× between runs of
  the same task), so small tests only catch
  large effects.

## What we think

- **Trust is the bottleneck, not retrieval.** Agents verify what they're
  given by reading the source again. Good context and accurate memory only
  save money once the agent may rely on them, which makes reviewing what
  goes into memory the real work.
- **Look at where the money goes first.** For the newer model, 46% of cost
  was storing newly read context, 38% was output and 16% was re-sending old
  context. Pruning could only touch the 16%; thinking less cut the output.
- **Measure, don't extrapolate.** The biggest saving on paper vanished when
  the model changed.
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
