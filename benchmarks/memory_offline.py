"""Offline upper bound for the memory experiment (no model calls).

For each follow-up task, ask the context service once with the task text and
measure label recall and package size, first with an empty memory, then after
recording "ideal" findings for the parent task: one per parent label, the
claim being the label's note and the evidence the range's first non-blank
line. Real agents will record fewer, vaguer findings, so this is a ceiling for
what one request_context call can gain from memory.

Usage: uv run python benchmarks/memory_offline.py
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from context_orchestrator.agent_interface.api import ContextService
from context_orchestrator.evaluation.retrieval_eval import load_suite
from context_orchestrator.models import InfoKind

ROOT = Path(__file__).resolve().parents[1]
FOLLOWUPS = ROOT / "benchmarks" / "tasks" / "hallpass_followups.json"
PARENTS = ROOT / "benchmarks" / "tasks" / "hallpass.json"


def recall(package, labels) -> float:
    hit = sum(1 for label in labels if any(label.overlaps(item.source) for item in package.items))
    return hit / len(labels)


def main() -> None:
    followups = load_suite(FOLLOWUPS)
    parents = {t.id: t for t in load_suite(PARENTS).tasks}
    after = {t["id"]: t["after"] for t in json.loads(FOLLOWUPS.read_text("utf-8"))["tasks"]}
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "base"
        with ContextService.without_telemetry(followups.project, base) as svc:
            svc.ingest()
        for task in followups.tasks:
            state = Path(tmp) / task.id
            shutil.copytree(base, state)
            with ContextService.without_telemetry(followups.project, state) as svc:
                request = {"task": task.task, "hops": 2}
                before = svc.request(request)
                for label in parents[after[task.id]].relevant:
                    lines = (followups.project / label.path).read_text("utf-8").splitlines()
                    span = lines[label.line_start - 1 : label.line_end]
                    first = next((x.strip() for x in span if x.strip()), "")[:200]
                    claim = f"{label.note} ({label.path})"
                    svc.record_finding(claim, label.path, label.line_start, label.line_end, first)
                with_memory = svc.request(request)
            rows.append(
                {
                    "task": task.id,
                    "recall_empty": round(recall(before, task.relevant), 3),
                    "recall_memory": round(recall(with_memory, task.relevant), 3),
                    "tokens_empty": before.estimated_tokens.value,
                    "tokens_memory": with_memory.estimated_tokens.value,
                    "findings_served": sum(i.kind is InfoKind.FINDING for i in with_memory.items),
                }
            )
    print(
        "| Task | Recall, empty memory | Recall, ideal parent memory | Findings served | "
        "Package tokens (est.) |"
    )
    print("|---|---|---|---|---|")
    for r in rows:
        print(
            f"| {r['task']} | {r['recall_empty']} | {r['recall_memory']} | "
            f"{r['findings_served']} | {r['tokens_empty']} -> {r['tokens_memory']} |"
        )
    n = len(rows)
    empty = sum(r["recall_empty"] for r in rows) / n
    print(f"\nMean recall {empty:.2f} -> {sum(r['recall_memory'] for r in rows) / n:.2f}")


if __name__ == "__main__":
    main()
