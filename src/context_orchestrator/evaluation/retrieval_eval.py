"""Phase 1: retrieval-only evaluation against hand-labelled tasks (no model involved).

A task suite (JSON, see ``benchmarks/tasks/``) lists tasks with the line ranges
an agent needs (``relevant``), ranges it must not be given (``forbidden``) and
kinds the service should report as missing (``expected_unresolved``). Labels
are line ranges rather than chunk ids, so they survive changes to chunking.

Scoring rules:

* A returned item *covers* a label when it comes from the same file and the
  line ranges overlap.
* recall = covered relevant labels / relevant labels (None if a task has none).
* precision = returned items covering any relevant label / returned items
  (None if nothing was returned: undefined, not zero).
* Precision is pessimistic: useful items nobody labelled count against it.

Every run writes raw, unmodified results to ``<out>/<run_id>/`` so they can be
analysed independently of this code.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from context_orchestrator import __version__
from context_orchestrator.agent_interface.api import ContextService
from context_orchestrator.models import (
    DEFAULT_MAX_REFERENCES,
    DEFAULT_MIN_RELATIVE_SCORE,
    ContextRequest,
    InfoKind,
    SourceRef,
    Status,
)
from context_orchestrator.telemetry.events import JsonlTelemetry
from context_orchestrator.tokens import ESTIMATE_METHOD, estimate_tokens

SUITE_SCHEMA_VERSION = 1
RESULT_SCHEMA_VERSION = 1
AGENT_ID = "eval-retrieval"


@dataclass(frozen=True, slots=True)
class Label:
    path: str
    line_start: int
    line_end: int
    note: str = ""
    expected_status: Status | None = None

    def overlaps(self, ref: SourceRef) -> bool:
        return (
            ref.path == self.path
            and ref.line_start <= self.line_end
            and self.line_start <= ref.line_end
        )

    def label(self) -> str:
        return f"{self.path}:{self.line_start}-{self.line_end}"


@dataclass(frozen=True, slots=True)
class EvalTask:
    id: str
    category: str
    task: str
    kinds: list[InfoKind]
    constraints: list[str]
    relevant: list[Label]
    forbidden: list[Label]
    expected_unresolved: list[str]


@dataclass(slots=True)
class TaskSuite:
    name: str
    path: Path
    project: Path
    sha256: str
    tasks: list[EvalTask]


@dataclass(frozen=True, slots=True)
class RetrievalConfig:
    max_tokens: int = 4000
    per_kind_limit: int = 3
    min_relative_score: float = DEFAULT_MIN_RELATIVE_SCORE
    max_references: int = DEFAULT_MAX_REFERENCES


# -- loading and validation ------------------------------------------------------


def _parse_label(raw: dict[str, Any], where: str, problems: list[str]) -> Label | None:
    try:
        start, end = raw["lines"]
        status = raw.get("expected_status")
        return Label(
            path=raw["path"],
            line_start=int(start),
            line_end=int(end),
            note=raw.get("note", ""),
            expected_status=Status(status) if status else None,
        )
    except (KeyError, TypeError, ValueError) as exc:
        problems.append(f"{where}: invalid label {raw!r} ({exc})")
        return None


def load_suite(path: Path | str) -> TaskSuite:
    """Load a task suite and check every label against the project files.

    All problems are collected and reported together, so stale labels (for
    example after the fixture changed) are caught before any scoring.
    """
    path = Path(path)
    data_bytes = path.read_bytes()
    data = json.loads(data_bytes)
    problems: list[str] = []
    if data.get("schema_version") != SUITE_SCHEMA_VERSION:
        problems.append(f"schema_version must be {SUITE_SCHEMA_VERSION}")
    project = (path.parent / data.get("project", "")).resolve()
    if not project.is_dir():
        raise ValueError(f"{path}: project directory not found: {project}")

    line_counts: dict[str, int | None] = {}

    def check(label: Label, where: str) -> None:
        if label.path not in line_counts:
            file = project / label.path
            line_counts[label.path] = (
                len(file.read_text(encoding="utf-8").splitlines()) if file.is_file() else None
            )
        count = line_counts[label.path]
        if count is None:
            problems.append(f"{where}: file not found: {label.path}")
        elif not 1 <= label.line_start <= label.line_end <= count:
            problems.append(
                f"{where}: lines {label.line_start}-{label.line_end} outside "
                f"{label.path} (1-{count})"
            )

    tasks: list[EvalTask] = []
    seen_ids: set[str] = set()
    for i, raw in enumerate(data.get("tasks", [])):
        where = f"task {raw.get('id', f'#{i}')}"
        task_id = raw.get("id")
        if not task_id or task_id in seen_ids:
            problems.append(f"{where}: missing or duplicate id")
        seen_ids.add(task_id)
        try:
            kinds = [InfoKind(k) for k in raw.get("kinds", [])]
            expected_unresolved = [InfoKind(k).value for k in raw.get("expected_unresolved", [])]
        except ValueError as exc:
            problems.append(f"{where}: {exc}")
            continue
        relevant = [_parse_label(r, where, problems) for r in raw.get("relevant", [])]
        forbidden = [_parse_label(r, where, problems) for r in raw.get("forbidden", [])]
        labels = [lab for lab in relevant + forbidden if lab is not None]
        for lab in labels:
            check(lab, where)
        if not relevant and not expected_unresolved:
            problems.append(f"{where}: needs relevant labels or expected_unresolved")
        if not str(raw.get("task", "")).strip():
            problems.append(f"{where}: empty task text")
        tasks.append(
            EvalTask(
                id=str(task_id),
                category=raw.get("category", "uncategorised"),
                task=raw.get("task", ""),
                kinds=kinds,
                constraints=list(raw.get("constraints", [])),
                relevant=[lab for lab in relevant if lab is not None],
                forbidden=[lab for lab in forbidden if lab is not None],
                expected_unresolved=expected_unresolved,
            )
        )
    if not tasks:
        problems.append("suite has no tasks")
    if problems:
        raise ValueError(f"{path}: invalid task suite:\n  " + "\n  ".join(problems))
    return TaskSuite(
        name=data.get("suite", path.stem),
        path=path,
        project=project,
        sha256=hashlib.sha256(data_bytes).hexdigest(),
        tasks=tasks,
    )


# -- scoring ---------------------------------------------------------------------


def evaluate_task(service: ContextService, task: EvalTask, config: RetrievalConfig) -> dict:
    request = ContextRequest(
        task=task.task,
        kinds=list(task.kinds),
        constraints=list(task.constraints),
        agent_id=AGENT_ID,
        max_tokens=config.max_tokens,
        per_kind_limit=config.per_kind_limit,
        min_relative_score=config.min_relative_score,
        max_references=config.max_references,
    )
    started = time.perf_counter()
    package = service.request(request)
    latency_ms = (time.perf_counter() - started) * 1000

    items = package.items
    covered = [lab for lab in task.relevant if any(lab.overlaps(i.source) for i in items)]
    is_relevant = [any(lab.overlaps(i.source) for lab in task.relevant) for i in items]
    status_mismatches = [
        {"label": lab.label(), "expected": lab.expected_status.value, "got": i.status.value}
        for lab in task.relevant
        if lab.expected_status is not None
        for i in items
        if lab.overlaps(i.source) and i.status is not lab.expected_status
    ]
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "task_id": task.id,
        "category": task.category,
        "request_id": package.request_id,
        "recall": len(covered) / len(task.relevant) if task.relevant else None,
        "precision": sum(is_relevant) / len(items) if items else None,
        "first_relevant_rank": next((n for n, r in enumerate(is_relevant, 1) if r), None),
        "n_items": len(items),
        "n_relevant_labels": len(task.relevant),
        "covered": [lab.label() for lab in covered],
        "missed": [lab.label() for lab in task.relevant if lab not in covered],
        "forbidden_returned": [
            lab.label() for lab in task.forbidden if any(lab.overlaps(i.source) for i in items)
        ],
        "status_mismatches": status_mismatches,
        "unresolved_kinds": list(package.unresolved_kinds),
        "unresolved_misses": [
            k for k in task.expected_unresolved if k not in package.unresolved_kinds
        ],
        "unexpected_unresolved": [
            k for k in package.unresolved_kinds if k not in task.expected_unresolved
        ],
        "package_tokens": asdict(package.estimated_tokens),
        "latency_ms": {
            "value": round(latency_ms, 3),
            "kind": "measured",
            "method": "time.perf_counter around ContextService.request",
        },
        "query_terms": list(package.query_terms),
        "items": [
            {
                "source": item.source.label(),
                "kind": item.kind.value,
                "status": item.status.value,
                "score": item.score,
                "matched_terms": list(item.matched_terms),
                "estimated_tokens": item.estimated_tokens,
                "relevant": rel,
            }
            for item, rel in zip(items, is_relevant, strict=True)
        ],
        "omitted": [{"source": o.source.label(), "reason": o.reason} for o in package.omitted],
    }


def _mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 4) if values else None


def summarize(results: list[dict], full_corpus_tokens: int) -> dict:
    recalls = [r["recall"] for r in results if r["recall"] is not None]
    precisions = [r["precision"] for r in results if r["precision"] is not None]
    package_tokens = [r["package_tokens"]["value"] for r in results]
    ratios = [t / full_corpus_tokens for t in package_tokens] if full_corpus_tokens else []
    by_category: dict[str, list[float]] = {}
    for r in results:
        if r["recall"] is not None:
            by_category.setdefault(r["category"], []).append(r["recall"])
    return {
        "n_tasks": len(results),
        "n_tasks_with_recall": len(recalls),
        "n_tasks_with_precision": len(precisions),
        "mean_recall": _mean(recalls),
        "min_recall": min(recalls) if recalls else None,
        "mean_precision": _mean(precisions),
        "recall_by_category": {k: _mean(v) for k, v in sorted(by_category.items())},
        "forbidden_returned": sum(len(r["forbidden_returned"]) for r in results),
        "unresolved_misses": sum(len(r["unresolved_misses"]) for r in results),
        "status_mismatches": sum(len(r["status_mismatches"]) for r in results),
        "mean_package_tokens": _mean(package_tokens),
        "full_corpus_tokens": full_corpus_tokens,
        "mean_package_to_corpus_ratio": _mean(ratios),
        "token_note": f"package and corpus tokens are estimates ({ESTIMATE_METHOD})",
    }


_OPS = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
}


def evaluate_gate(gate: dict, summary: dict) -> dict:
    """Check summary metrics against a gate definition. Missing metrics fail."""
    outcomes = []
    for c in gate["criteria"]:
        actual = summary.get(c["metric"])
        passed = actual is not None and _OPS[c["op"]](actual, c["value"])
        outcomes.append({**c, "actual": actual, "passed": passed})
    return {
        "gate": gate.get("gate"),
        "passed": all(o["passed"] for o in outcomes),
        "criteria": outcomes,
    }


# -- running -----------------------------------------------------------------------


def _git_state(cwd: Path) -> dict[str, Any]:
    def git(*args: str) -> str | None:
        try:
            out = subprocess.run(
                ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=10, check=True
            )
            return out.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None

    commit = git("rev-parse", "HEAD")
    # Only tracked changes count: untracked output (e.g. other run folders) cannot alter the code.
    status = git("status", "--porcelain", "--untracked-files=no")
    return {"commit": commit, "dirty": None if status is None else bool(status)}


def _corpus_tokens(service: ContextService) -> int:
    return sum(estimate_tokens(chunk.text) for chunk in service.store.iter_chunks())


@dataclass(slots=True)
class RunResult:
    run_dir: Path
    summary: dict
    gate: dict | None
    results: list[dict] = field(default_factory=list)


def run_suite(
    suite: TaskSuite,
    out_dir: Path | str,
    config: RetrievalConfig | None = None,
    gate: dict | None = None,
    gate_path: Path | None = None,
) -> RunResult:
    """Ingest the suite's project into a fresh store, score every task, write raw files."""
    config = config or RetrievalConfig()
    git_state = _git_state(suite.path.resolve().parent)  # before this run writes any files
    started_at = datetime.now(UTC)
    run_id = f"{started_at:%Y%m%dT%H%M%SZ}-{suite.name}"
    run_dir = Path(out_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as state:
        telemetry = JsonlTelemetry(run_dir / "telemetry.jsonl", record_task_text=True)
        with ContextService(suite.project, state, telemetry=telemetry) as service:
            ingest = service.ingest()
            corpus_tokens = _corpus_tokens(service)
            chunk_count = service.store.count_chunks()
            results = [evaluate_task(service, task, config) for task in suite.tasks]

    with (run_dir / "results.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for r in results:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

    summary = summarize(results, corpus_tokens)
    gate_result = evaluate_gate(gate, summary) if gate else None
    run_meta = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "run_id": run_id,
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "tool_version": __version__,
        "git": git_state,
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "sqlite": sqlite3.sqlite_version,
        },
        "suite": {
            "name": suite.name,
            "path": suite.path.as_posix(),
            "sha256": suite.sha256,
            "n_tasks": len(suite.tasks),
        },
        "gate_file": (
            {
                "path": gate_path.as_posix(),
                "sha256": hashlib.sha256(gate_path.read_bytes()).hexdigest(),
            }
            if gate_path
            else None
        ),
        "config": asdict(config),
        "corpus": {
            "files": len(ingest.added),
            "chunks": chunk_count,
            "estimated_tokens": corpus_tokens,
        },
        "summary": summary,
        "gate": gate_result,
    }
    # newline="\n": raw files are byte-identical on every OS.
    (run_dir / "run.json").write_text(
        json.dumps(run_meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    (run_dir / "summary.md").write_text(
        render_summary(run_meta, results), encoding="utf-8", newline="\n"
    )
    return RunResult(run_dir, summary, gate_result, results)


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def render_summary(run_meta: dict, results: list[dict]) -> str:
    s = run_meta["summary"]
    git = run_meta["git"]
    lines = [
        f"# Retrieval evaluation: {run_meta['suite']['name']}",
        "",
        f"- Run: `{run_meta['run_id']}`, commit `{(git['commit'] or 'unknown')[:10]}`"
        + (" (uncommitted changes present)" if git["dirty"] else ""),
        f"- Config: max_tokens={run_meta['config']['max_tokens']}, "
        f"per_kind_limit={run_meta['config']['per_kind_limit']}, "
        f"min_relative_score={run_meta['config'].get('min_relative_score', 0.0)}, "
        f"max_references={run_meta['config'].get('max_references', 0)}",
        f"- Corpus: {run_meta['corpus']['files']} files, {run_meta['corpus']['chunks']} chunks, "
        f"~{run_meta['corpus']['estimated_tokens']} tokens (estimated)",
        "",
        "| Task | Category | Recall | Precision | First hit | Items | ~Tokens | Missed |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['task_id']} | {r['category']} | {_fmt(r['recall'])} | {_fmt(r['precision'])} "
            f"| {r['first_relevant_rank'] or 'none'} | {r['n_items']} "
            f"| {r['package_tokens']['value']} | {', '.join(r['missed']) or '-'} |"
        )
    lines += [
        "",
        f"Mean recall {_fmt(s['mean_recall'])}, mean precision {_fmt(s['mean_precision'])}, "
        f"mean package ~{s['mean_package_tokens']:.0f} tokens = "
        f"{_fmt(s['mean_package_to_corpus_ratio'])} of the full corpus.",
        f"Forbidden items returned: {s['forbidden_returned']}. "
        f"Expected-unresolved misses: {s['unresolved_misses']}. "
        f"Status mismatches: {s['status_mismatches']}.",
        "",
        "Recall by category: "
        + ", ".join(f"{k} {_fmt(v)}" for k, v in s["recall_by_category"].items()),
    ]
    gate = run_meta.get("gate")
    if gate:
        lines += [
            "",
            f"## {gate['gate']}: {'PASSED' if gate['passed'] else 'NOT PASSED'}",
            "",
            "| Criterion | Metric | Target | Actual | Result |",
            "|---|---|---|---|---|",
        ]
        for c in gate["criteria"]:
            actual = c["actual"]
            shown = _fmt(actual) if isinstance(actual, float) else actual
            lines.append(
                f"| {c['id']} | {c['metric']} | {c['op']} {c['value']} | {shown} "
                f"| {'pass' if c['passed'] else 'FAIL'} |"
            )
    return "\n".join(lines) + "\n"
