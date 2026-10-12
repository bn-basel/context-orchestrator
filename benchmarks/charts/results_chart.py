"""Draw the results chart (light and dark SVG) from the published run folders.

Usage: uv run python benchmarks/charts/results_chart.py

One bar per idea: the change in cost against the same agent without it, with
a plain verdict derived from the 95% bootstrap interval and the score change
(the same rules as the write-up). Ideas that work are highlighted. Two groups,
each against its own baseline:

* Claude Code + Haiku 4.5 (phase 2, 300 runs): each strategy against the
  agent exploring alone; intervals over tasks, from the run's analysis.json.
* Our own agent loop + Haiku 5.5 (phases 4-5): each lever against the same loop
  without it (pruning, outline reads and low effort vs plain; memory vs empty
  memory); intervals over (task, repetition) pairs, computed from runs.jsonl.

Standard library only.
"""

from __future__ import annotations

import json
import math
import random
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "benchmarks" / "results"
PHASE2 = RESULTS / "20261011T032628Z-hallpass-agent"
PRUNE = [RESULTS / "20261011T071428Z-loop-prune"]
MEMORY = [RESULTS / "20261011T072205Z-loop-memory", RESULTS / "20261011T073027Z-loop-memory"]
READS = [RESULTS / "20261012T022153Z-loop-prune"]  # L, LC (outline reads), LE (effort low)
TRUST = [RESULTS / "20261012T023255Z-loop-trust", RESULTS / "20261012T024550Z-loop-trust"]
# Phase 6 (L, S, X) and phase 7 (L, S, SE, TR): combinations against a plain agent.
COMBO = [RESULTS / "20261012T034938Z-loop-combo", RESULTS / "20261012T050712Z-loop-combo"]
RESAMPLES, SEED = 10_000, 20261011

FONT = 'font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif"'


# -- data ------------------------------------------------------------------------------------


def _bootstrap_mean(values: list[float]) -> tuple[float, float]:
    rng = random.Random(SEED)
    means = sorted(statistics.fmean(rng.choices(values, k=len(values))) for _ in range(RESAMPLES))
    return means[int(0.025 * RESAMPLES)], means[int(0.975 * RESAMPLES) - 1]


def loop_pairs(run_dirs: list[Path], arm: str, base: str) -> dict:
    """Cost ratio and score difference of `arm` vs `base`, paired by (task, repetition)."""
    logs, diffs, runs, charged = [], [], 0, 0.0
    for run_dir in run_dirs:
        rows = [json.loads(x) for x in (run_dir / "runs.jsonl").read_text("utf-8").splitlines()]
        runs += len(rows)
        charged += sum(r["usage"]["measured_cost_usd"]["value"] for r in rows)
        rows = {(r["task_id"], r["repetition"], r["arm"]): r for r in rows
                if r["role"] == "task" and not r["error"]}  # fmt: skip
        for (task, rep, a), r in rows.items():
            other = rows.get((task, rep, base))
            if a != arm or other is None:
                continue
            cost = (r["usage"]["measured_cost_usd"]["value"],
                    other["usage"]["measured_cost_usd"]["value"])  # fmt: skip
            logs.append(math.log(cost[0] / cost[1]))
            diffs.append(r["grade"]["score"] - other["grade"]["score"])
    lo, hi = _bootstrap_mean(logs)
    s_lo, s_hi = _bootstrap_mean(diffs)
    return {
        "cost": (math.exp(statistics.fmean(logs)), [math.exp(lo), math.exp(hi)]),
        "score": (statistics.fmean(diffs), [s_lo, s_hi]),
        "pairs": len(logs),
        "runs": runs,
        "charged": charged,
    }


def collect() -> dict:
    analysis = json.loads((PHASE2 / "analysis.json").read_text("utf-8"))
    meta = json.loads((PHASE2 / "run.json").read_text("utf-8"))
    comps = analysis["comparisons"]

    def phase2(key: str) -> dict:
        c = comps[f"{key} vs C"]
        return {
            "cost": (c["cost_ratio"]["ratio"], c["cost_ratio"]["ci95"]),
            "score": (c["score"]["mean_difference"], c["score"]["ci95"]),
        }

    prune = loop_pairs(PRUNE, "LP", "L")
    memory = loop_pairs(MEMORY, "SM", "SM0")
    outline = loop_pairs(READS, "LC", "L")
    effort = loop_pairs(READS, "LE", "L")
    trust = loop_pairs(TRUST, "TR", "T0")
    service = loop_pairs(COMBO, "S", "L")  # pooled over both combo runs
    service_low = loop_pairs(COMBO[1:], "SE", "L")
    all_three = loop_pairs(COMBO[:1], "X", "L")
    # Each run folder counted once: READS via effort, COMBO via service.
    loop = [prune, memory, effort, trust, service]
    summary = meta["summary"]
    return {
        "values": {k: phase2(k) for k in ("A", "B", "B2", "D")}
        | {"prune": prune, "memory": memory, "outline": outline, "effort": effort,
           "trust": trust, "service": service, "service_low": service_low,
           "all_three": all_three},
        "phase2_runs": sum(v["runs"] for v in summary.values()),
        "phase2_cost": sum(v["total_api_equivalent_cost_usd"] for v in summary.values()),
        "phase2_tasks": analysis["tasks"],
        "loop_runs": sum(x["runs"] for x in loop),
        "loop_charged": sum(x["charged"] for x in loop),
    }  # fmt: skip


THEMES = {
    "light": {"text": "#0b0b0b", "muted": "#52514e", "grid": "#d9d8d4",
              "good": "#2a78d6", "other": "#b9b8b3", "zero": "#52514e"},
    "dark": {"text": "#ffffff", "muted": "#c3c2b7", "grid": "#3a3a37",
             "good": "#3987e5", "other": "#5f5e5a", "zero": "#c3c2b7"},
}  # fmt: skip

LABEL_W, BAR_X0, BAR_W, ROW, GROUP = 300, 330, 300, 40, 46
LO, HI = -0.5, 1.0  # cost change shown from -50% to +100%


def verdict(key: str, v: dict) -> tuple[str, bool]:
    """(text, works) from the cost interval and the score change, as in the write-up."""
    mid, (lo, hi) = v["cost"]
    score = v["score"][0]
    if key == "D":
        return "best case, not buildable", False
    if lo > 1:
        return "costs more", False
    if mid >= 1.10:
        return "no saving, likely costs more", False
    if hi < 1:
        if score >= -0.03:
            return "works, same quality", True
        if score >= -0.05:
            return "works, slightly less thorough", True
        if score >= -0.06:
            return "quality just under the bar", False
        return "cheaper, but lower quality", False
    return ("inconclusive" if mid <= 0.92 else "no clear saving"), False


ROWS = [
    ("head", "GIVING THE AGENT PROJECT CONTEXT"),
    ("row", "B2", "Ask a context service first"),
    ("row", "B", "Offer the service (agent may skip it)"),
    ("row", "A", "Put the whole project in the prompt"),
    ("row", "D", "Hand over exactly the right pieces"),
    ("head", "CHANGING HOW THE AGENT WORKS"),
    ("row", "effort", "Think less (low effort setting)"),
    ("row", "trust", "Memory of earlier tasks, reviewed"),
    ("row", "outline", "Show long files as an outline first"),
    ("row", "memory", "Memory of earlier tasks, unreviewed"),
    ("row", "prune", "Prune old context as it works"),
    ("head", "COMBINED, AGAINST A PLAIN AGENT"),
    ("row", "service", "Ask the service first"),
    ("row", "service_low", "... and think less"),
    ("row", "all_three", "... and think less and trust memory"),
]


# The README chart: only the headline and the trade-offs, every row against a plain agent
# that explores the files itself (Claude Code for the whole-project row, our loop otherwise).
SIMPLE_ROWS = [
    ("row", "service", "Ask a context service first"),
    ("row", "service_low", "... and think less"),
    ("row", "all_three", "... and also trust reviewed memory"),
    ("row", "prune", "Prune old context as it works"),
    ("row", "A", "Put the whole project in the prompt"),
]
SIMPLE_VERDICTS = {
    "service": ("same quality", True),
    "service_low": ("slightly lower quality", False),
    "all_three": ("lower quality", False),
    "prune": ("no saving", False),
    "A": ("costs double", False),
}
VIEWS = {
    "results": {
        "rows": SIMPLE_ROWS,
        "verdicts": SIMPLE_VERDICTS,
        "title": "How to make a coding agent cheaper",
        "subtitle": "Change in cost vs. a plain agent that reads the files itself",
        "notes": [
            "Left of the line = cheaper. Highlighted = cheaper with the same plan quality "
            "(95% intervals, plans graded by fixed rubrics).",
            "Our own agent loop on one project; the whole-project row is from a separate 300-run "
            "study. All results: docs/findings.md",
        ],
    },
    "results-detail": {
        "rows": ROWS,
        "verdicts": {},
        "title": "What actually cut a coding agent’s cost? (all results)",
        "subtitle": "Change in cost vs. the same agent without the idea",
        "notes": [
            "Left of the line = cheaper. Highlighted = the saving is clear (95% interval) and plan "
            "quality held. Each group has its own baseline.",
            "First group: an existing coding agent, 300 runs. Other groups: our own agent loop on "
            "a newer model.",
        ],
    },
}


def render(d: dict, theme: str, view: dict) -> str:
    c = THEMES[theme]
    rows = view["rows"]
    W = 900
    top = 104
    ys, y = [], top
    for kind, *_ in rows:
        h = GROUP if kind == "head" else ROW
        ys.append(y + h / 2)
        y += h
    bottom = y
    height = bottom + 70

    def x(change: float) -> float:
        return BAR_X0 + (min(max(change, LO), HI) - LO) / (HI - LO) * BAR_W

    total_runs = d["phase2_runs"] + d["loop_runs"]
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height:.0f}" '
        f'viewBox="0 0 {W} {height:.0f}" role="img" aria-labelledby="t d">',
        f'<title id="t">{view["title"]}</title>',
        f'<desc id="d">{view["subtitle"]}: one bar per setup with a verdict on plan '
        "quality.</desc>",
        f'<text x="24" y="38" fill="{c["text"]}" font-size="22" font-weight="600" {FONT}>'
        f"{view['title']}</text>",
        f'<text x="24" y="64" fill="{c["muted"]}" font-size="14" {FONT}>'
        f"{view['subtitle']} · {total_runs} graded runs</text>",
    ]
    x0 = x(0)
    for t in (-0.5, 0, 0.5, 1.0):
        tick = "0" if t == 0 else f"{t:+.0%}".replace("-", "−")
        svg.append(f'<text x="{x(t):.1f}" y="{top - 8}" fill="{c["muted"]}" font-size="12" '
                   f'text-anchor="middle" {FONT}>{tick}</text>')  # fmt: skip
    for (kind, *rest), yc in zip(rows, ys, strict=True):
        if kind == "head":
            head = f'font-size="12" font-weight="600" letter-spacing="0.5" {FONT}'
            svg.append(f'<text x="24" y="{yc + 9:.1f}" fill="{c["muted"]}" {head}>{rest[0]}</text>')
            continue
        key, label = rest
        v = d["values"][key]
        change = v["cost"][0] - 1
        text, works = view["verdicts"].get(key) or verdict(key, v)
        fill = c["good"] if works else c["other"]
        xa, xb = sorted((x0, x(change)))
        svg.append(f'<text x="24" y="{yc + 5:.1f}" fill="{c["text"]}" font-size="15" '
                   f"{FONT}>{label}</text>")  # fmt: skip
        svg.append(f'<rect x="{xa:.1f}" y="{yc - 9:.1f}" width="{max(xb - xa, 2):.1f}" '
                   f'height="18" rx="3" fill="{fill}"/>')  # fmt: skip
        pct = f"{change:+.0%}".replace("-", "−")
        vx, anchor = (xb + 8, "start") if change >= 0 else (xa - 8, "end")
        svg.append(f'<text x="{vx:.1f}" y="{yc + 5:.1f}" fill="{c["text"]}" font-size="14" '
                   f'font-weight="600" text-anchor="{anchor}" {FONT}>{pct}</text>')  # fmt: skip
        weight = "600" if works else "400"
        color = c["text"] if works else c["muted"]
        svg.append(f'<text x="{BAR_X0 + BAR_W + 70}" y="{yc + 5:.1f}" fill="{color}" '
                   f'font-size="14" font-weight="{weight}" {FONT}>{text}</text>')  # fmt: skip
    svg.append(f'<line x1="{x0:.1f}" y1="{top}" x2="{x0:.1f}" y2="{bottom}" '
               f'stroke="{c["zero"]}" stroke-width="1.5"/>')  # fmt: skip
    for i, note in enumerate(view["notes"]):
        svg.append(f'<text x="24" y="{bottom + 30 + 18 * i:.0f}" fill="{c["muted"]}" '
                   f'font-size="12" {FONT}>{note}</text>')  # fmt: skip
    svg.append("</svg>")
    return "\n".join(svg) + "\n"


def main() -> None:
    d = collect()
    out = ROOT / "docs" / "img"
    out.mkdir(parents=True, exist_ok=True)
    for name, view in VIEWS.items():
        for theme in THEMES:
            path = out / f"{name}-{theme}.svg"
            path.write_text(render(d, theme, view), encoding="utf-8", newline="\n")
            print(path)
    for _, key, label in (r for r in ROWS if r[0] == "row"):
        v = d["values"][key]
        print(f"{label}: {v['cost'][0] - 1:+.1%} -> {verdict(key, v)[0]}")


if __name__ == "__main__":
    main()
