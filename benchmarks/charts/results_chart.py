"""Draw the results chart (light and dark SVG) from the published run folders.

Usage: uv run python benchmarks/charts/results_chart.py

Two panels sharing the rows (never a dual axis): cost relative to a baseline,
and the change in plan score against it, each as a dot with its 95% bootstrap
interval. Two groups of rows, each against its own baseline:

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
RESAMPLES, SEED = 10_000, 20261011

THEMES = {
    "light": {"text": "#0b0b0b", "muted": "#52514e", "grid": "#d9d8d4",
              "mark": "#2a78d6", "base": "#8b8a86"},
    "dark": {"text": "#ffffff", "muted": "#c3c2b7", "grid": "#3a3a37",
             "mark": "#3987e5", "base": "#8b8a86"},
}  # fmt: skip

W, ROW_H, HEAD_H, TOP, LEFT = 900, 42, 40, 96, 262
PANEL_W, GAP = 270, 70
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
    loop = [prune, memory, effort, trust]  # READS counted once (outline and effort share it)
    summary = meta["summary"]
    return {
        "values": {k: phase2(k) for k in ("A", "B", "B2", "D")}
        | {"prune": prune, "memory": memory, "outline": outline, "effort": effort,
           "trust": trust},
        "phase2_runs": sum(v["runs"] for v in summary.values()),
        "phase2_cost": sum(v["total_api_equivalent_cost_usd"] for v in summary.values()),
        "phase2_tasks": analysis["tasks"],
        "loop_runs": sum(x["runs"] for x in loop),
        "loop_charged": sum(x["charged"] for x in loop),
    }  # fmt: skip


def layout(d: dict) -> list[tuple]:
    """Rows top to bottom: ("head", text) or ("row", key, label); key None = baseline."""
    return [
        ("head", f"Claude Code, Haiku 4.5 · {d['phase2_runs']} runs · vs. the agent "
                 "exploring alone"),
        ("row", "A", "Whole project in the prompt"),
        ("row", None, "Agent explores alone (baseline)"),
        ("row", "B", "Context service, offered"),
        ("row", "B2", "Context service, used first"),
        ("row", "D", "Oracle: exactly the needed pieces"),
        ("head", f"Own agent loop, Haiku 5.5 · {d['loop_runs']} runs · vs. the same loop "
                 "without it"),
        *[("row", key, f"{label} ({d['values'][key]['pairs']} pairs)") for key, label in (
            ("effort", "Low effort, less thinking"),
            ("trust", "Trusted, reviewed memory"),
            ("outline", "Outline-first file reads"),
            ("memory", "Memory, unreviewed"),
            ("prune", "Pruning old tool output"),
        )],
    ]  # fmt: skip


# -- drawing ---------------------------------------------------------------------------------


def _positions(rows: list[tuple]) -> tuple[list[float], float]:
    ys, y = [], TOP
    for row in rows:
        h = HEAD_H if row[0] == "head" else ROW_H
        ys.append(y + h / 2)
        y += h
    return ys, y


def _x(value: float, lo: float, hi: float, x0: float) -> float:
    return x0 + (min(max(value, lo), hi) - lo) / (hi - lo) * PANEL_W


def _panel(svg: list[str], c: dict, rows: list[tuple], ys: list[float], bottom: float,
           title: str, x0: float, lo: float, hi: float, ticks: list[float], fmt, ref: float,
           metric: str, values: dict) -> None:  # fmt: skip
    svg.append(f'<text x="{x0}" y="{TOP - 14}" fill="{c["text"]}" font-size="14" '
               f'font-weight="600" {FONT}>{title}</text>')  # fmt: skip
    # Vertical lines run through each group's rows only, never through a group heading.
    heads = [y for row, y in zip(rows, ys, strict=True) if row[0] == "head"]
    spans = [(h + 13, (heads[i + 1] - HEAD_H / 2) if i + 1 < len(heads) else bottom)
             for i, h in enumerate(heads)]  # fmt: skip
    xr = _x(ref, lo, hi, x0)
    for t in ticks:
        x = _x(t, lo, hi, x0)
        for y1, y2 in spans:
            svg.append(f'<line x1="{x:.1f}" y1="{y1:.1f}" x2="{x:.1f}" y2="{y2:.1f}" '
                       f'stroke="{c["grid"]}" stroke-width="1"/>')  # fmt: skip
        svg.append(f'<text x="{x:.1f}" y="{bottom + 18}" fill="{c["muted"]}" font-size="12" '
                   f'text-anchor="middle" {FONT}>{fmt(t)}</text>')  # fmt: skip
    dash = f'stroke="{c["muted"]}" stroke-width="1.5" stroke-dasharray="4 4"'
    for y1, y2 in spans:
        svg.append(f'<line x1="{xr:.1f}" y1="{y1:.1f}" x2="{xr:.1f}" y2="{y2:.1f}" {dash}/>')
    for row, y in zip(rows, ys, strict=True):
        if row[0] == "head":
            continue
        key = row[1]
        if key is None:
            svg.append(f'<circle cx="{xr:.1f}" cy="{y:.1f}" r="5" fill="{c["base"]}"/>')
            continue
        mid, (low, high) = values[key][metric]
        x1, x2, xm = _x(low, lo, hi, x0), _x(high, lo, hi, x0), _x(mid, lo, hi, x0)
        svg.append(f'<line x1="{x1:.1f}" y1="{y:.1f}" x2="{x2:.1f}" y2="{y:.1f}" '
                   f'stroke="{c["mark"]}" stroke-width="2" stroke-linecap="round"/>')  # fmt: skip
        svg.append(f'<circle cx="{xm:.1f}" cy="{y:.1f}" r="5" fill="{c["mark"]}"/>')
        # Label beyond the interval end facing away from the reference line.
        lx, anchor = (x2 + 8, "start") if mid >= ref else (x1 - 8, "end")
        svg.append(f'<text x="{lx:.1f}" y="{y + 4:.1f}" fill="{c["text"]}" font-size="12" '
                   f'text-anchor="{anchor}" {FONT}>{fmt(mid)}</text>')  # fmt: skip


def render(d: dict, theme: str) -> str:
    c = THEMES[theme]
    rows = layout(d)
    ys, bottom = _positions(rows)
    height = bottom + 92
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height:.0f}" '
        f'viewBox="0 0 {W} {height:.0f}" role="img" aria-labelledby="t d">',
        f'<title id="t">Context strategies, pruning and memory compared on '
        f"{d['phase2_runs'] + d['loop_runs']} agent runs</title>",
        '<desc id="d">Cost relative to a baseline and change in plan score, with 95% '
        "intervals: five ways of giving a coding agent project context (Claude Code, "
        "Haiku 4.5), and five cost levers in our own agent loop (Haiku 5.5).</desc>",
        f'<text x="24" y="34" fill="{c["text"]}" font-size="20" font-weight="600" {FONT}>'
        "How should a coding agent get project context?</text>",
        f'<text x="24" y="58" fill="{c["muted"]}" font-size="13" {FONT}>'
        f"{d['phase2_runs'] + d['loop_runs']} runs on one synthetic project · "
        f"${d['phase2_cost']:.0f} API-equivalent (Claude Code) + "
        f"${d['loop_charged']:.2f} charged (own loop)</text>",
    ]
    for row, y in zip(rows, ys, strict=True):
        if row[0] == "head":
            svg.append(f'<text x="24" y="{y + 5:.1f}" fill="{c["muted"]}" font-size="12" '
                       f'font-weight="600" {FONT}>{row[1].upper()}</text>')  # fmt: skip
            svg.append(f'<line x1="24" y1="{y + 13:.1f}" x2="{W - 24}" y2="{y + 13:.1f}" '
                       f'stroke="{c["grid"]}" stroke-width="1"/>')  # fmt: skip
        else:
            svg.append(f'<text x="24" y="{y + 4:.1f}" fill="{c["text"]}" font-size="14" '
                       f"{FONT}>{row[2]}</text>")  # fmt: skip
    common = (svg, c, rows, ys, bottom)
    _panel(*common, "Cost vs. baseline", LEFT, 0, 2.5, [0, 0.5, 1, 1.5, 2, 2.5],
           lambda v: f"{v:g}×" if v in (0, 0.5, 1, 1.5, 2, 2.5) else f"{v:.2f}×", 1.0,
           "cost", d["values"])  # fmt: skip
    _panel(*common, "Plan score vs. baseline", LEFT + PANEL_W + GAP, -0.2, 0.2,
           [-0.2, -0.1, 0, 0.1, 0.2], lambda v: f"{v:+.2f}" if round(v, 2) else "0", 0.0, "score",
           d["values"])  # fmt: skip
    foot = bottom + 50
    notes = [
        "Dots: paired estimates; lines: 95% bootstrap intervals. Each group has its own "
        "baseline; the groups differ in harness and model.",
        "Claude Code cost is its list-price estimate, not a subscription charge; own-loop "
        "cost is OpenRouter's charge. Details: docs/findings.md",
    ]
    for i, note in enumerate(notes):
        svg.append(f'<text x="24" y="{foot + 18 * i}" fill="{c["muted"]}" font-size="12" '
                   f"{FONT}>{note}</text>")  # fmt: skip
    svg.append("</svg>")
    return "\n".join(svg) + "\n"


def main() -> None:
    d = collect()
    out = ROOT / "docs" / "img"
    out.mkdir(parents=True, exist_ok=True)
    for theme in THEMES:
        path = out / f"results-{theme}.svg"
        path.write_text(render(d, theme), encoding="utf-8", newline="\n")
        print(path)
    for key in ("effort", "trust", "outline", "memory", "prune"):
        v = d["values"][key]
        print(key, "cost", v["cost"], "score", v["score"], "pairs", v["pairs"])


if __name__ == "__main__":
    main()
