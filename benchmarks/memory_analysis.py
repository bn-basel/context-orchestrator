"""Paired analysis of loop-memory runs: memory (SM) vs empty memory (SM0) follow-ups.

Pairs are (task, repetition): the follow-up on its parent's memory against the
same follow-up on an empty memory from the same repetition. For tokens and
measured cost it reports the geometric-mean ratio with a 95% bootstrap interval
over pairs, how many pairs were cheaper with memory, and the score difference.
Several run folders can be pooled (repetitions are kept apart per folder).

Usage: uv run python benchmarks/memory_analysis.py benchmarks/results/<run> [...]
"""

from __future__ import annotations

import json
import math
import random
import statistics
import sys
from pathlib import Path

RESAMPLES = 10_000
SEED = 20261011


def load_pairs(run_dirs: list[Path]) -> list[dict]:
    pairs = []
    for run_dir in run_dirs:
        rows = [json.loads(x) for x in (run_dir / "runs.jsonl").read_text("utf-8").splitlines()]
        rows = [r for r in rows if r["role"] == "task" and not r["error"]]
        by_key = {(r["task_id"], r["repetition"], r["arm"]): r for r in rows}
        for (task, rep, arm), r in sorted(by_key.items()):
            other = by_key.get((task, rep, "SM0"))
            if arm != "SM" or other is None:
                continue
            pairs.append(
                {
                    "run": run_dir.name,
                    "task": task,
                    "rep": rep,
                    "tokens": (r["usage"]["total_input_tokens"]["value"],
                               other["usage"]["total_input_tokens"]["value"]),
                    "cost": (r["usage"]["measured_cost_usd"]["value"],
                             other["usage"]["measured_cost_usd"]["value"]),
                    "score": (r["grade"]["score"], other["grade"]["score"]),
                }
            )  # fmt: skip
    return pairs


def ratio_with_interval(logs: list[float]) -> tuple[float, float, float]:
    rng = random.Random(SEED)
    means = sorted(
        statistics.fmean(rng.choices(logs, k=len(logs))) for _ in range(RESAMPLES)
    )  # fmt: skip
    lo, hi = means[int(0.025 * RESAMPLES)], means[int(0.975 * RESAMPLES) - 1]
    return math.exp(statistics.fmean(logs)), math.exp(lo), math.exp(hi)


def main(args: list[str]) -> None:
    pairs = load_pairs([Path(a) for a in args])
    print(f"{len(pairs)} pairs from {len(args)} run folder(s)\n")
    print(
        "| Measure | Memory / empty (geometric mean) | 95% interval "
        "| Pairs cheaper or smaller with memory |"
    )
    print("|---|---|---|---|")
    for key in ("tokens", "cost"):
        logs = [math.log(p[key][0] / p[key][1]) for p in pairs if p[key][0] and p[key][1]]
        mid, lo, hi = ratio_with_interval(logs)
        wins = sum(1 for x in logs if x < 0)
        print(f"| {key} | ×{mid:.2f} | ×{lo:.2f} – ×{hi:.2f} | {wins} of {len(logs)} |")
    diffs = [p["score"][0] - p["score"][1] for p in pairs]
    print(f"\nMean score difference (memory − empty): {statistics.fmean(diffs):+.3f}; "
          f"memory better in {sum(d > 0 for d in diffs)}, worse in {sum(d < 0 for d in diffs)}, "
          f"equal in {sum(d == 0 for d in diffs)} pairs")  # fmt: skip
    print("\n| Task | Pairs | Cost ratio (geometric mean) |")
    print("|---|---|---|")
    for task in sorted({p["task"] for p in pairs}):
        logs = [math.log(p["cost"][0] / p["cost"][1]) for p in pairs if p["task"] == task]
        print(f"| {task} | {len(logs)} | ×{math.exp(statistics.fmean(logs)):.2f} |")


if __name__ == "__main__":
    main(sys.argv[1:])
