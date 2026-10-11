"""Analyse an agent-comparison run from its raw ``runs.jsonl`` only.

Strategies are compared *paired by task*: for every task, a strategy's mean
over repetitions is compared with the baseline's mean on the same task, so
task difficulty cancels out. Uncertainty comes from a bootstrap over tasks
(resampling the 20 tasks with replacement, seeded), giving a 95% interval for
the mean difference. An interval that contains 0 means the run cannot tell
the two strategies apart on that measure.

Token comparisons use the ratio of per-task medians (geometric mean of the
ratios, bootstrapped the same way), because token counts are skewed.
"""

from __future__ import annotations

import json
import math
import random
import statistics
from pathlib import Path
from typing import Any

BOOTSTRAP_SAMPLES = 10_000
SEED = 20261011


def load_runs(run_dir: Path) -> list[dict[str, Any]]:
    """Latest attempt per (task, strategy, repetition), successful runs only."""
    latest: dict[tuple, dict[str, Any]] = {}
    for line in (run_dir / "runs.jsonl").read_text(encoding="utf-8").splitlines():
        if line:
            r = json.loads(line)
            latest[(r["task_id"], r["strategy"], r["repetition"])] = r
    return [r for r in latest.values() if not r["error"]]


def per_task(runs: list[dict[str, Any]], metric: str) -> dict[str, dict[str, float]]:
    """strategy -> task -> mean score, or median value of a usage metric."""
    grouped: dict[str, dict[str, list[float]]] = {}
    for r in runs:
        if metric == "score":
            value = r["grade"]["score"]
        elif metric == "success":
            value = 1.0 if r["grade"]["success"] else 0.0
        else:
            value = r["usage"][metric]["value"]
        if value is None:
            continue
        grouped.setdefault(r["strategy"], {}).setdefault(r["task_id"], []).append(value)
    agg = statistics.fmean if metric in ("score", "success") else statistics.median
    return {s: {t: agg(v) for t, v in tasks.items()} for s, tasks in grouped.items()}


def _bootstrap(values: list[float], rng: random.Random) -> tuple[float, float]:
    n = len(values)
    means = sorted(
        statistics.fmean(rng.choice(values) for _ in range(n)) for _ in range(BOOTSTRAP_SAMPLES)
    )
    return means[int(0.025 * BOOTSTRAP_SAMPLES)], means[int(0.975 * BOOTSTRAP_SAMPLES) - 1]


def paired_difference(
    table: dict[str, dict[str, float]], strategy: str, baseline: str
) -> dict[str, Any]:
    tasks = sorted(set(table[strategy]) & set(table[baseline]))
    diffs = [table[strategy][t] - table[baseline][t] for t in tasks]
    low, high = _bootstrap(diffs, random.Random(SEED))
    return {"tasks": len(tasks), "mean_difference": statistics.fmean(diffs), "ci95": (low, high)}


def paired_ratio(
    table: dict[str, dict[str, float]], strategy: str, baseline: str
) -> dict[str, Any]:
    tasks = sorted(t for t in set(table[strategy]) & set(table[baseline]) if table[baseline][t] > 0)
    logs = [math.log(table[strategy][t] / table[baseline][t]) for t in tasks]
    low, high = _bootstrap(logs, random.Random(SEED))
    return {
        "tasks": len(tasks),
        "ratio": math.exp(statistics.fmean(logs)),
        "ci95": (math.exp(low), math.exp(high)),
    }


def service_use(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out = {}
    for strategy in sorted({r["strategy"] for r in runs}):
        rows = [r for r in runs if r["strategy"] == strategy]
        used = [r for r in rows if r["service_calls"] > 0]
        file_calls = [sum(1 for c in r["tool_calls"] if not c.startswith("mcp__")) for r in rows]
        out[strategy] = {
            "runs": len(rows),
            "runs_using_service": len(used),
            "mean_service_calls": statistics.fmean(r["service_calls"] for r in rows),
            "median_file_tool_calls": statistics.median(file_calls),
        }
    return out


def analyse(run_dir: Path, baselines: tuple[str, ...] = ("C", "A")) -> dict[str, Any]:
    runs = load_runs(run_dir)
    scores = per_task(runs, "score")
    successes = per_task(runs, "success")
    tokens = per_task(runs, "total_input_tokens")
    costs = per_task(runs, "api_equivalent_cost_usd")
    strategies = sorted(scores)
    comparisons: dict[str, dict[str, Any]] = {}
    for base in baselines:
        if base not in scores:
            continue
        for s in strategies:
            if s == base:
                continue
            comparisons[f"{s} vs {base}"] = {
                "score": paired_difference(scores, s, base),
                "success_rate": paired_difference(successes, s, base),
                "input_tokens_ratio": paired_ratio(tokens, s, base),
                "cost_ratio": paired_ratio(costs, s, base),
            }
    return {
        "runs_analysed": len(runs),
        "tasks": len({r["task_id"] for r in runs}),
        "method": __doc__.strip().splitlines()[0],
        "bootstrap": {"samples": BOOTSTRAP_SAMPLES, "seed": SEED, "unit": "task"},
        "service_use": service_use(runs),
        "comparisons": comparisons,
    }


def render(analysis: dict[str, Any]) -> str:
    def diff(d: dict[str, Any]) -> str:
        low, high = d["ci95"]
        return f"{d['mean_difference']:+.3f} [{low:+.3f}, {high:+.3f}]"

    def ratio(d: dict[str, Any]) -> str:
        low, high = d["ci95"]
        return f"{d['ratio']:.2f}x [{low:.2f}, {high:.2f}]"

    boot = analysis["bootstrap"]
    lines = [
        "# Paired analysis",
        "",
        f"{analysis['runs_analysed']} successful runs over {analysis['tasks']} tasks. "
        "Differences are per-task paired; 95% intervals from a bootstrap over tasks "
        f"({boot['samples']} samples, seed {boot['seed']}). "
        "An interval containing 0 (or 1.00 for ratios) means no detectable difference.",
        "",
        "| Comparison | Score difference [95% CI] | Success-rate difference [95% CI] | "
        "Input-token ratio [95% CI] | Cost ratio [95% CI] |",
        "|---|---|---|---|---|",
    ]
    for name, c in analysis["comparisons"].items():
        lines.append(
            f"| {name} | {diff(c['score'])} | {diff(c['success_rate'])} | "
            f"{ratio(c['input_tokens_ratio'])} | {ratio(c['cost_ratio'])} |"
        )
    lines += ["", "| Strategy | Runs | Runs using the service | Mean service calls | "
              "Median file-tool calls |", "|---|---|---|---|---|"]  # fmt: skip
    for s, u in analysis["service_use"].items():
        lines.append(
            f"| {s} | {u['runs']} | {u['runs_using_service']} | {u['mean_service_calls']:.2f} | "
            f"{u['median_file_tool_calls']} |"
        )
    return "\n".join(lines) + "\n"


def write_analysis(run_dir: Path) -> Path:
    analysis = analyse(run_dir)
    (run_dir / "analysis.json").write_text(
        json.dumps(analysis, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    out = run_dir / "analysis.md"
    out.write_text(render(analysis), encoding="utf-8", newline="\n")
    return out
