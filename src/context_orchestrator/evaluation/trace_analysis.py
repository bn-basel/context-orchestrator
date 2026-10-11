"""What did agents read, and why? Analysis of raw ``claude -p`` event streams.

For each run, every file read is classified against two references:

* what the context service had already handed over in that run (the
  ``(path:start-end)`` headings of its answers), and
* the task's labelled relevant ranges.

Classes, checked in this order:

* ``served`` - the read covers a range the service already returned (the
  agent wanted more than the excerpt, or re-read it);
* ``needed_missed`` - the read covers a labelled range the service had not
  returned: the agent recovering a retrieval miss;
* ``same_file`` - another part of a file the service pointed to;
* ``unrelated`` - none of the above.

Cost proxy: tool output stays in the conversation and is re-sent with every
later model call, so each result is weighted by the number of tool calls that
follow it ("carried characters"). Input tokens grow with this, not with the
raw size alone.
"""

from __future__ import annotations

import gzip
import json
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from context_orchestrator.evaluation.retrieval_eval import Label, TaskSuite

SERVICE_TOOL = "mcp__ctxo__request_context"
_SERVED = re.compile(r"^## .*\(([^()\s]+):(\d+)-(\d+)\)\s*$", re.MULTILINE)
_PREFIX = re.compile(r"^<workspace>[\\/]+project[\\/]+")
CLASSES = ("served", "needed_missed", "same_file", "unrelated")
# Strategies that receive context in the prompt: "never seen" by reading is meaningless.
PROMPT_CONTEXT_STRATEGIES = ("A", "D")


@dataclass(slots=True)
class Call:
    tool: str
    path: str | None  # project-relative POSIX path for reads
    span: tuple[int, int] | None  # line range read; None = from the start, unbounded
    result_chars: int
    carried_chars: int = 0
    klass: str | None = None
    served: list[tuple[str, int, int]] = field(default_factory=list)  # service calls only


@dataclass(slots=True)
class RunTrace:
    task_id: str
    strategy: str
    repetition: int
    score: float | None
    calls: list[Call] = field(default_factory=list)
    served: list[tuple[str, int, int]] = field(default_factory=list)


def _relative(path: str) -> str:
    return _PREFIX.sub("", path).replace("\\", "/")


def _span(inp: dict[str, Any]) -> tuple[int, int] | None:
    offset, limit = inp.get("offset"), inp.get("limit")
    if offset is None and limit is None:
        return None
    start = int(offset or 1)
    return (start, start + int(limit) - 1) if limit else (start, 10**9)


def _overlaps(span: tuple[int, int] | None, start: int, end: int) -> bool:
    if span is None:
        return True
    return span[0] <= end and start <= span[1]


def parse_trace(text: str) -> tuple[list[Call], list[tuple[str, int, int]]]:
    """Tool calls in order (with result sizes) and the ranges the service returned."""
    calls: list[Call] = []
    by_id: dict[str, Call] = {}
    served: list[tuple[str, int, int]] = []
    for line in text.splitlines():
        if not line.startswith("{"):
            continue
        content = json.loads(line).get("message", {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if block.get("type") == "tool_use":
                inp = block.get("input") or {}
                call = Call(
                    tool=block.get("name", "?"),
                    path=_relative(inp["file_path"]) if block.get("name") == "Read" else None,
                    span=_span(inp) if block.get("name") == "Read" else None,
                    result_chars=0,
                )
                calls.append(call)
                by_id[block.get("id")] = call
            elif block.get("type") == "tool_result" and block.get("tool_use_id") in by_id:
                call = by_id[block["tool_use_id"]]
                body = block.get("content")
                if isinstance(body, list):
                    body = "".join(b.get("text", "") for b in body if isinstance(b, dict))
                body = body if isinstance(body, str) else json.dumps(body)
                call.result_chars = len(body)
                if call.tool == SERVICE_TOOL:
                    call.served = [(p, int(a), int(b)) for p, a, b in _SERVED.findall(body)]
                    served += call.served
    for index, call in enumerate(calls):
        call.carried_chars = call.result_chars * (len(calls) - index)
    return calls, served


def classify(trace: RunTrace, labels: list[Label]) -> None:
    """Classify each Read against what the service had returned *before* it."""
    served_so_far: list[tuple[str, int, int]] = []
    for call in trace.calls:
        if call.tool == SERVICE_TOOL:
            served_so_far = served_so_far + call.served
            continue
        if call.tool != "Read" or call.path is None:
            continue
        hit_served = any(p == call.path and _overlaps(call.span, a, b) for p, a, b in served_so_far)
        missed = any(
            lab.path == call.path
            and _overlaps(call.span, lab.line_start, lab.line_end)
            and not any(p == lab.path and a <= lab.line_end and lab.line_start <= b
                        for p, a, b in served_so_far)
            for lab in labels
        )  # fmt: skip
        if hit_served:
            call.klass = "served"
        elif missed:
            call.klass = "needed_missed"
        elif any(p == call.path for p, _, _ in served_so_far):
            call.klass = "same_file"
        else:
            call.klass = "unrelated"


def load_traces(run_dir: Path, suite: TaskSuite) -> list[RunTrace]:
    labels = {t.id: t.relevant for t in suite.tasks}
    latest: dict[tuple, dict[str, Any]] = {}
    for line in (run_dir / "runs.jsonl").read_text(encoding="utf-8").splitlines():
        if line:
            r = json.loads(line)
            latest[(r["task_id"], r["strategy"], r["repetition"])] = r
    traces = []
    for (task, strategy, rep), record in sorted(latest.items()):
        if record["error"]:
            continue
        raw = run_dir / "raw" / f"{task}-{strategy}-{rep}.jsonl.gz"
        calls, served = parse_trace(gzip.decompress(raw.read_bytes()).decode("utf-8"))
        trace = RunTrace(task, strategy, rep, record["grade"]["score"], calls, served)
        classify(trace, labels[task])
        traces.append(trace)
    return traces


def label_coverage(trace: RunTrace, labels: list[Label]) -> dict[str, int]:
    """How each labelled range reached the agent: served, read by itself, or never seen."""
    out = {"served": 0, "read_only": 0, "unseen": 0}
    reads = [c for c in trace.calls if c.tool == "Read"]
    for lab in labels:
        start, end = lab.line_start, lab.line_end
        if any(p == lab.path and a <= end and start <= b for p, a, b in trace.served):
            out["served"] += 1
        elif any(c.path == lab.path and _overlaps(c.span, start, end) for c in reads):
            out["read_only"] += 1
        else:
            out["unseen"] += 1
    return out


def summarise(traces: list[RunTrace], suite: TaskSuite) -> dict[str, Any]:
    labels = {t.id: t.relevant for t in suite.tasks}
    out: dict[str, Any] = {}
    for strategy in sorted({t.strategy for t in traces}):
        rows = [t for t in traces if t.strategy == strategy]
        reads = [c for t in rows for c in t.calls if c.tool == "Read"]
        carried_total = sum(c.carried_chars for t in rows for c in t.calls)
        by_tool: dict[str, int] = {}
        for t in rows:
            for c in t.calls:
                by_tool[c.tool] = by_tool.get(c.tool, 0) + c.carried_chars
        by_class = {k: [c for c in reads if c.klass == k] for k in CLASSES}
        coverage = {"served": 0, "read_only": 0, "unseen": 0}
        for t in rows:
            for k, v in label_coverage(t, labels[t.task_id]).items():
                coverage[k] += v
        n_labels = sum(coverage.values()) or 1
        out[strategy] = {
            "runs": len(rows),
            "reads_per_run": round(len(reads) / len(rows), 2),
            "read_chars_per_run": round(sum(c.result_chars for c in reads) / len(rows)),
            "carried_share_by_tool": {
                k: round(v / carried_total, 3) for k, v in sorted(by_tool.items()) if carried_total
            },
            "reads_by_class": {k: len(v) for k, v in by_class.items()},
            "read_chars_by_class": {k: sum(c.result_chars for c in v) for k, v in by_class.items()},
            "label_coverage": {k: round(v / n_labels, 3) for k, v in coverage.items()},
            "mean_score_by_unseen_labels": _score_by_unseen(rows, labels),
        }
    return out


def _score_by_unseen(rows: list[RunTrace], labels: dict[str, list[Label]]) -> dict[str, Any]:
    groups: dict[str, list[float]] = {"0": [], "1": [], "2+": []}
    for t in rows:
        unseen = label_coverage(t, labels[t.task_id])["unseen"]
        if t.score is not None:
            groups["0" if unseen == 0 else "1" if unseen == 1 else "2+"].append(t.score)
    return {k: (round(statistics.fmean(v), 3) if v else None, len(v)) for k, v in groups.items()}


def render(summary: dict[str, Any]) -> str:
    lines = [
        "# What agents read",
        "",
        "Reads classified against what the service had already returned in the run and the "
        "task's labelled ranges. 'Carried' = result size x later tool calls (it is re-sent "
        "with each), a proxy for its input-token cost.",
        "",
        "| Strategy | Reads/run | Read chars/run | Reads: served / needed-missed / same file "
        "/ unrelated | Share of carried context: Read / Grep / Glob / service |",
        "|---|---|---|---|---|",
    ]
    for s, v in summary.items():
        r = v["reads_by_class"]
        share = v["carried_share_by_tool"]
        lines.append(
            f"| {s} | {v['reads_per_run']} | {v['read_chars_per_run']:,} | "
            f"{r['served']} / {r['needed_missed']} / {r['same_file']} / {r['unrelated']} | "
            f"{share.get('Read', 0):.0%} / {share.get('Grep', 0):.0%} / "
            f"{share.get('Glob', 0):.0%} / {share.get(SERVICE_TOOL, 0):.0%} |"
        )
    lines += [
        "",
        "| Strategy | Labelled ranges: served by service / read by the agent only / never seen "
        "| Mean score when 0 / 1 / 2+ labelled ranges were never seen (runs) |",
        "|---|---|---|",
    ]
    for s, v in summary.items():
        c = v["label_coverage"]
        g = v["mean_score_by_unseen_labels"]
        if s in PROMPT_CONTEXT_STRATEGIES:
            lines.append(f"| {s} | n/a (context given in the prompt) | n/a |")
            continue
        lines.append(
            f"| {s} | {c['served']:.0%} / {c['read_only']:.0%} / {c['unseen']:.0%} | "
            + " / ".join(f"{g[k][0]} ({g[k][1]})" for k in ("0", "1", "2+"))
            + " |"
        )
    return "\n".join(lines) + "\n"


def write_trace_analysis(run_dir: Path, suite: TaskSuite) -> Path:
    summary = summarise(load_traces(run_dir, suite), suite)
    (run_dir / "traces.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    out = run_dir / "traces.md"
    out.write_text(render(summary), encoding="utf-8", newline="\n")
    return out
