"""Draw the phase 2 results chart (light and dark SVG) from a run's analysis.json.

Usage: uv run python benchmarks/charts/phase2_chart.py benchmarks/results/<run>

Two panels sharing the strategy rows (never a dual axis): cost relative to
the "explores alone" baseline, and the change in plan score against it, each
as a dot with its 95% bootstrap interval over tasks. Standard library only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROWS = [  # (strategy key, label) - ordered from most to least context handed over
    ("A", "Whole project in the prompt"),
    ("C", "Agent explores alone (baseline)"),
    ("B", "Context service, offered"),
    ("B2", "Context service, used first"),
    ("D", "Oracle: exactly the needed pieces"),
]
BASELINE = "C"
# `--model haiku` resolved to claude-haiku-4-5 in these runs (see raw/*.jsonl.gz, modelUsage).
MODEL_LABEL = "Haiku 4.5"

THEMES = {
    "light": {"text": "#0b0b0b", "muted": "#52514e", "grid": "#d9d8d4",
              "mark": "#2a78d6", "base": "#8b8a86"},
    "dark": {"text": "#ffffff", "muted": "#c3c2b7", "grid": "#3a3a37",
             "mark": "#3987e5", "base": "#8b8a86"},
}  # fmt: skip

W, ROW_H, TOP, LEFT = 900, 46, 112, 262
PANEL_W, GAP = 270, 70
FONT = 'font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif"'


def _x(value: float, lo: float, hi: float, x0: float) -> float:
    return x0 + (value - lo) / (hi - lo) * PANEL_W


def _panel(svg: list[str], c: dict, title: str, x0: float, lo: float, hi: float,
           ticks: list[float], fmt, ref: float, values: dict) -> None:  # fmt: skip
    bottom = TOP + ROW_H * len(ROWS)
    svg.append(f'<text x="{x0}" y="{TOP - 30}" fill="{c["text"]}" font-size="14" '
               f'font-weight="600" {FONT}>{title}</text>')  # fmt: skip
    for t in ticks:
        x = _x(t, lo, hi, x0)
        svg.append(f'<line x1="{x:.1f}" y1="{TOP - 12}" x2="{x:.1f}" y2="{bottom}" '
                   f'stroke="{c["grid"]}" stroke-width="1"/>')  # fmt: skip
        svg.append(f'<text x="{x:.1f}" y="{bottom + 18}" fill="{c["muted"]}" font-size="12" '
                   f'text-anchor="middle" {FONT}>{fmt(t)}</text>')  # fmt: skip
    xr = _x(ref, lo, hi, x0)
    svg.append(f'<line x1="{xr:.1f}" y1="{TOP - 12}" x2="{xr:.1f}" y2="{bottom}" '
               f'stroke="{c["muted"]}" stroke-width="1.5" stroke-dasharray="4 4"/>')  # fmt: skip
    for i, (key, _) in enumerate(ROWS):
        y = TOP + ROW_H * i + ROW_H / 2
        if key == BASELINE:
            svg.append(f'<circle cx="{xr:.1f}" cy="{y:.1f}" r="5" fill="{c["base"]}"/>')
            continue
        mid, (low, high) = values[key]
        x1, x2, xm = _x(low, lo, hi, x0), _x(high, lo, hi, x0), _x(mid, lo, hi, x0)
        svg.append(f'<line x1="{x1:.1f}" y1="{y:.1f}" x2="{x2:.1f}" y2="{y:.1f}" '
                   f'stroke="{c["mark"]}" stroke-width="2" stroke-linecap="round"/>')  # fmt: skip
        svg.append(f'<circle cx="{xm:.1f}" cy="{y:.1f}" r="5" fill="{c["mark"]}"/>')
        # Label beyond the interval end facing away from the reference line, so it never
        # crosses the dashed baseline.
        lx, anchor = (x2 + 8, "start") if mid >= ref else (x1 - 8, "end")
        svg.append(f'<text x="{lx:.1f}" y="{y + 4:.1f}" fill="{c["text"]}" font-size="12" '
                   f'text-anchor="{anchor}" {FONT}>{fmt(mid)}</text>')  # fmt: skip


def render(analysis: dict, run: dict, theme: str) -> str:
    c = THEMES[theme]
    comps = analysis["comparisons"]

    def interval(key: str, metric: str, value: str) -> tuple[float, list[float]]:
        entry = comps[f"{key} vs {BASELINE}"][metric]
        return entry[value], entry["ci95"]

    shown = [k for k, _ in ROWS if k != BASELINE]
    cost = {k: interval(k, "cost_ratio", "ratio") for k in shown}
    score = {k: interval(k, "score", "mean_difference") for k in shown}
    summary = run["summary"]
    n_runs = sum(v["runs"] for v in summary.values())
    total_cost = sum(v["total_api_equivalent_cost_usd"] for v in summary.values())
    height = TOP + ROW_H * len(ROWS) + 78
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height}" '
        f'viewBox="0 0 {W} {height}" role="img" aria-labelledby="t d">',
        f'<title id="t">Context strategies compared on {n_runs} Claude Code runs</title>',
        '<desc id="d">Cost relative to an agent exploring alone, and change in plan score, '
        "for five ways of giving a coding agent project context, with 95% intervals.</desc>",
        f'<text x="24" y="34" fill="{c["text"]}" font-size="20" font-weight="600" {FONT}>'
        "How should a coding agent get project context?</text>",
        f'<text x="24" y="58" fill="{c["muted"]}" font-size="13" {FONT}>'
        f"{n_runs} Claude Code runs ({MODEL_LABEL}) · {analysis['tasks']} tasks × "
        f"{len(summary)} strategies × {run['config']['repetitions']} · "
        f"${total_cost:.0f} API-equivalent in total</text>",
    ]
    for i, (_, label) in enumerate(ROWS):
        y = TOP + ROW_H * i + ROW_H / 2 + 4
        svg.append(f'<text x="24" y="{y:.1f}" fill="{c["text"]}" font-size="14" {FONT}>'
                   f"{label}</text>")  # fmt: skip
    _panel(
        svg,
        c,
        "Cost vs. exploring alone",
        LEFT,
        0,
        2.5,
        [0, 0.5, 1, 1.5, 2, 2.5],
        lambda v: f"{v:.2f}×" if v not in (0, 0.5, 1, 1.5, 2, 2.5) else f"{v:g}×",
        1.0,
        cost,
    )
    _panel(
        svg,
        c,
        "Plan score vs. exploring alone",
        LEFT + PANEL_W + GAP,
        -0.15,
        0.15,
        [-0.1, 0, 0.1],
        lambda v: f"{v:+.2f}" if v else "0",
        0.0,
        score,
    )
    foot = TOP + ROW_H * len(ROWS) + 50
    svg.append(
        f'<text x="24" y="{foot}" fill="{c["muted"]}" font-size="12" {FONT}>'
        "Dots: per-task paired estimates; lines: 95% bootstrap intervals over tasks. "
        "Cost is Claude Code's API list-price estimate, not a subscription charge.</text>"
    )
    svg.append(f'<text x="24" y="{foot + 18}" fill="{c["muted"]}" font-size="12" {FONT}>'
               "One synthetic ~140k-token project; plans graded by rubrics fixed before the runs. "
               "Details: docs/findings.md</text>")  # fmt: skip
    svg.append("</svg>")
    return "\n".join(svg) + "\n"


def main(run_dir: str) -> None:
    run = Path(run_dir)
    analysis = json.loads((run / "analysis.json").read_text(encoding="utf-8"))
    meta = json.loads((run / "run.json").read_text(encoding="utf-8"))
    out = Path(__file__).resolve().parents[2] / "docs" / "img"
    out.mkdir(parents=True, exist_ok=True)
    for theme in THEMES:
        path = out / f"phase2-results-{theme}.svg"
        path.write_text(render(analysis, meta, theme), encoding="utf-8", newline="\n")
        print(path)


if __name__ == "__main__":
    main(sys.argv[1])
