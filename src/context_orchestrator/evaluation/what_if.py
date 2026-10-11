"""Counterfactual estimates from recorded agent runs (no model calls).

Each policy is replayed over the recorded tool calls of a run and its effect on
*carried context* is computed: a tool result of ``n`` characters followed by
``k`` more tool calls is re-sent ``k`` times, so it contributes ``n * k``.
How carried context translates into input tokens is fitted on the same runs,
separately per strategy (``input_tokens ~ a * model_calls + b * carried_chars``,
least squares without intercept): ``a`` is the fixed per-call overhead (system
prompt, tools; ~180k for the full-context strategy), ``b`` the cost of carried
tool output.

These are estimates under a strong assumption: **the agent would otherwise
behave the same.** Real agents react to what they receive (phase 3a showed
compact excerpts made agents read more), so an estimate is an upper bound
on what a policy could save, used to decide what is worth a small real test.

Policies:

* ``whole_files(T)`` - the service returns the whole file instead of a chunk
  when the file has at most T characters. Saves later reads of that file;
  costs the extra file text from the service call onwards.
* ``complete_first_answer`` - the first service answer already contains the
  labelled ranges the agent later read for itself. Saves those reads; costs
  the range text from the first service call onwards. (An upper bound for
  better retrieval or better follow-up answers.)
* ``targeted_reads`` - whole-file re-reads of files the service pointed to
  become ~50-line reads (a "file map" letting the agent read only what it
  needs). Upper bound.
* ``prune_after(K)`` - every tool result is replaced by a one-line stub after
  K further tool calls (in-place context editing). Saves the rest of its
  carried text; costs a re-read whenever the agent opens the same file again
  later, which is already in the recording, so no extra cost is assumed.
"""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any

from context_orchestrator.evaluation.retrieval_eval import TaskSuite
from context_orchestrator.evaluation.trace_analysis import SERVICE_TOOL, RunTrace, load_traces

STUB_CHARS = 80  # "[result of Read src/... removed; re-read if needed]"


def _carried(trace: RunTrace) -> int:
    return sum(c.carried_chars for c in trace.calls)


def fit_cost_model(traces: list[RunTrace], tokens: dict[tuple, int]) -> dict[str, float]:
    """Least squares for input_tokens = a * model_calls + b * carried_chars."""
    rows = []
    for t in traces:
        y = tokens.get((t.task_id, t.strategy, t.repetition))
        if y:
            rows.append((len(t.calls) + 1, _carried(t), y))
    sxx = sum(x1 * x1 for x1, _, _ in rows)
    szz = sum(x2 * x2 for _, x2, _ in rows)
    sxz = sum(x1 * x2 for x1, x2, _ in rows)
    sxy = sum(x1 * y for x1, _, y in rows)
    szy = sum(x2 * y for _, x2, y in rows)
    det = sxx * szz - sxz * sxz
    a = (sxy * szz - szy * sxz) / det
    b = (szy * sxx - sxy * sxz) / det
    pairs = [(a * x1 + b * x2, y) for x1, x2, y in rows if a * x1 + b * x2 > 0]
    r = statistics.correlation([math.log(p) for p, _ in pairs], [math.log(y) for _, y in pairs])
    return {
        "per_call_tokens": a,
        "tokens_per_carried_char": b,
        "log_correlation": r,
        "runs": len(rows),
    }


def _file_text(project: Path, path: str, cache: dict[str, list[str]]) -> list[str]:
    if path not in cache:
        file = project / path
        cache[path] = file.read_text(encoding="utf-8").splitlines() if file.is_file() else []
    return cache[path]


def _range_chars(lines: list[str], start: int, end: int) -> int:
    return sum(len(x) + 1 for x in lines[start - 1 : end])


def whole_files(trace: RunTrace, project: Path, threshold: int, cache: dict) -> int:
    """Change in carried chars if short served files were returned whole."""
    n = len(trace.calls)
    delta = 0
    upgraded: dict[str, int] = {}  # path -> index of the service call that returned it
    for i, call in enumerate(trace.calls):
        if call.tool != SERVICE_TOOL:
            continue
        served_chars: dict[str, int] = {}
        for path, a, b in call.served:
            lines = _file_text(project, path, cache)
            served_chars[path] = served_chars.get(path, 0) + _range_chars(lines, a, b)
        for path, chars in served_chars.items():
            size = sum(len(x) + 1 for x in _file_text(project, path, cache))
            if path in upgraded or not size or size > threshold:
                continue
            upgraded[path] = i
            delta += max(size - chars, 0) * (n - i)
    for i, call in enumerate(trace.calls):
        if call.tool == "Read" and call.path in upgraded and i > upgraded[call.path]:
            delta -= call.carried_chars
    return delta


def complete_first_answer(trace: RunTrace, labels: list, project: Path, cache: dict) -> int:
    services = [i for i, c in enumerate(trace.calls) if c.tool == SERVICE_TOOL]
    if not services:
        return 0
    first, n = services[0], len(trace.calls)
    delta = 0
    added: set[tuple] = set()
    for call in trace.calls[first + 1 :]:
        if call.tool != "Read" or call.klass != "needed_missed":
            continue
        delta -= call.carried_chars
        for lab in labels:
            key = (lab.path, lab.line_start, lab.line_end)
            if lab.path == call.path and key not in added:
                added.add(key)
                lines = _file_text(project, lab.path, cache)
                delta += _range_chars(lines, lab.line_start, lab.line_end) * (n - first)
    return delta


def targeted_reads(trace: RunTrace, max_chars: int = 2000) -> int:
    """Whole-file re-reads of files the service had pointed to become ~50-line reads.

    Upper bound for a "file map" (outline with line ranges) that lets the agent read
    only the part it needs.
    """
    delta = 0
    served_paths: set[str] = set()
    n = len(trace.calls)
    for i, call in enumerate(trace.calls):
        if call.tool == SERVICE_TOOL:
            served_paths |= {p for p, _, _ in call.served}
        elif (
            call.tool == "Read"
            and call.span is None
            and call.path in served_paths
            and call.result_chars > max_chars
        ):
            delta -= (call.result_chars - max_chars) * (n - i)
    return delta


def prune_after(trace: RunTrace, k: int) -> int:
    n = len(trace.calls)
    delta = 0
    for i, call in enumerate(trace.calls):
        remaining = n - i
        if remaining > k and call.result_chars > STUB_CHARS:
            delta -= (call.result_chars - STUB_CHARS) * (remaining - k)
    return delta


def estimate(run_dir: Path, suite: TaskSuite) -> dict[str, Any]:
    traces = load_traces(run_dir, suite)
    tokens = {}
    for line in (run_dir / "runs.jsonl").read_text(encoding="utf-8").splitlines():
        if line:
            r = json.loads(line)
            value = r["usage"]["total_input_tokens"]["value"]
            if value and not r["error"]:
                tokens[(r["task_id"], r["strategy"], r["repetition"])] = value
    models = {
        s: fit_cost_model([t for t in traces if t.strategy == s], tokens)
        for s in sorted({t.strategy for t in traces})
    }
    labels = {t.id: t.relevant for t in suite.tasks}
    cache: dict[str, list[str]] = {}

    def token_change(rows: list[RunTrace], fn) -> dict[str, float] | None:
        """Mean and median relative change in fitted input tokens across runs."""
        model = models[rows[0].strategy]
        b = model["tokens_per_carried_char"]
        changes = []
        for t in rows:
            base = model["per_call_tokens"] * (len(t.calls) + 1) + b * _carried(t)
            if base > 0:
                changes.append(b * fn(t) / base)
        if not changes:
            return None
        return {
            "mean": round(statistics.fmean(changes), 4),
            "median": round(statistics.median(changes), 4),
        }

    policies: dict[str, dict[str, Any]] = {}
    for strategy in sorted({t.strategy for t in traces}):
        rows = [t for t in traces if t.strategy == strategy]
        out: dict[str, Any] = {}
        if models[strategy]["tokens_per_carried_char"] <= 0:
            policies[strategy] = {"note": "fixed per-call cost dominates; no usable fit"}
            continue
        if any(c.tool == SERVICE_TOOL for t in rows for c in t.calls):
            for threshold in (4_000, 8_000, 16_000, 32_000):
                out[f"whole_files_{threshold // 1000}k"] = token_change(
                    rows, lambda t, th=threshold: whole_files(t, suite.project, th, cache)
                )
            out["targeted_reads_2k"] = token_change(rows, lambda t: targeted_reads(t, 2000))
            out["complete_first_answer"] = token_change(
                rows, lambda t: complete_first_answer(t, labels[t.task_id], suite.project, cache)
            )
        for k in (3, 5, 10):
            out[f"prune_after_{k}"] = token_change(rows, lambda t, k=k: prune_after(t, k))
        policies[strategy] = out
    return {"cost_models": models, "input_token_change": policies}


def render(result: dict[str, Any]) -> str:
    lines = [
        "# What-if estimates (replayed recordings, no model calls)",
        "",
        "Cost model per strategy: input tokens ≈ a per model call + b per carried character.",
        "",
        "| Strategy | Runs | a (tokens per call) | b (tokens per carried char) | "
        "Correlation, log predicted vs log actual |",
        "|---|---|---|---|---|",
    ]
    for s, m in result["cost_models"].items():
        lines.append(
            f"| {s} | {m['runs']} | {m['per_call_tokens']:,.0f} | "
            f"{m['tokens_per_carried_char']:.3f} | {m['log_correlation']:.2f} |"
        )
    lines += [
        "",
        "Change in input tokens per run, mean (median), **assuming the agent behaves "
        "the same otherwise** (an upper bound on savings). n/a: policy does not apply; "
        "-: no usable cost fit for that strategy.",
        "",
    ]
    policies = result["input_token_change"]
    names = sorted({p for v in policies.values() for p in v if p != "note"})
    lines.append("| Policy | " + " | ".join(policies) + " |")
    lines.append("|---|" + "---|" * len(policies))
    for name in names:
        cells = []
        for v in policies.values():
            x = v.get(name)
            if "note" in v:
                cells.append("-")
            elif x is None:
                cells.append("n/a")
            else:
                cells.append(f"{x['mean']:+.0%} ({x['median']:+.0%})")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def write_what_if(run_dir: Path, suite: TaskSuite) -> Path:
    result = estimate(run_dir, suite)
    (run_dir / "what_if.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    out = run_dir / "what_if.md"
    out.write_text(render(result), encoding="utf-8", newline="\n")
    return out
