import json
from pathlib import Path

import pytest

from context_orchestrator.agent_interface.cli import main
from context_orchestrator.evaluation.retrieval_eval import (
    Label,
    evaluate_gate,
    load_suite,
    run_suite,
    summarize,
)
from context_orchestrator.models import SourceRef

REPO_ROOT = Path(__file__).resolve().parents[1]
COMMITTED_SUITE = REPO_ROOT / "benchmarks" / "tasks" / "sample_project.json"
COMMITTED_GATE = REPO_ROOT / "benchmarks" / "gate1.json"


def _ref(path: str, start: int, end: int) -> SourceRef:
    return SourceRef(path, start, end, "0" * 64, "2026-01-01T00:00:00+00:00")


def test_label_overlap_rules() -> None:
    label = Label("a.md", 10, 20)
    assert label.overlaps(_ref("a.md", 20, 30))  # touching end
    assert label.overlaps(_ref("a.md", 1, 10))  # touching start
    assert label.overlaps(_ref("a.md", 12, 14))  # inside
    assert not label.overlaps(_ref("a.md", 21, 30))
    assert not label.overlaps(_ref("b.md", 10, 20))


def _write_suite(tmp_path: Path, tasks: list[dict]) -> Path:
    project = tmp_path / "proj"
    (project / "docs").mkdir(parents=True)
    (project / "docs" / "billing.md").write_text(
        "---\nkind: decision\nstatus: verified\n---\n"
        "# Billing\n\n## Invoices\nInvoices are numbered sequentially per year.\n\n"
        "## Refunds\nRefunds need manager approval.\n",
        encoding="utf-8",
    )
    (project / "docs" / "old.md").write_text(
        "---\nkind: decision\nstatus: superseded\n---\n"
        "# Old billing\n\nInvoices used random numbers.\n",
        encoding="utf-8",
    )
    suite = tmp_path / "suite.json"
    suite.write_text(
        json.dumps({"schema_version": 1, "suite": "tiny", "project": "proj", "tasks": tasks}),
        encoding="utf-8",
    )
    return suite


def test_scores_are_exact_on_a_known_case(tmp_path: Path) -> None:
    suite_path = _write_suite(
        tmp_path,
        [
            {
                "id": "A",
                "category": "c",
                "task": "how are invoices numbered",
                "kinds": ["decision", "finding"],
                "relevant": [
                    {"path": "docs/billing.md", "lines": [7, 8]},
                    {"path": "docs/billing.md", "lines": [10, 11]},
                ],
                "forbidden": [{"path": "docs/old.md", "lines": [5, 7]}],
                "expected_unresolved": ["finding"],
            }
        ],
    )
    run = run_suite(load_suite(suite_path), tmp_path / "out")
    r = run.results[0]
    # Only the Invoices section matches "invoices numbered"; Refunds is never returned.
    assert r["recall"] == 0.5
    assert r["missed"] == ["docs/billing.md:10-11"]
    assert r["precision"] == 1.0
    assert r["first_relevant_rank"] == 1
    assert r["forbidden_returned"] == []  # superseded decision withheld
    assert r["unresolved_misses"] == []
    assert run.summary["mean_recall"] == 0.5

    # Raw files exist and round-trip.
    files = {p.name for p in run.run_dir.iterdir()}
    assert files == {"run.json", "results.jsonl", "summary.md", "telemetry.jsonl"}
    meta = json.loads((run.run_dir / "run.json").read_text(encoding="utf-8"))
    assert meta["suite"]["sha256"] == load_suite(suite_path).sha256
    assert meta["corpus"]["chunks"] > 0
    lines = (run.run_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0])["task_id"] == "A"


def test_precision_is_undefined_not_zero_when_nothing_is_returned(tmp_path: Path) -> None:
    suite_path = _write_suite(
        tmp_path,
        [
            {
                "id": "B",
                "task": "kubernetes deployment manifests",
                "kinds": ["decision"],
                "relevant": [{"path": "docs/billing.md", "lines": [7, 8]}],
            }
        ],
    )
    r = run_suite(load_suite(suite_path), tmp_path / "out").results[0]
    assert r["n_items"] == 0
    assert r["precision"] is None
    assert r["recall"] == 0.0
    assert r["unexpected_unresolved"] == ["decision"]


def test_invalid_labels_are_all_reported(tmp_path: Path) -> None:
    suite_path = _write_suite(
        tmp_path,
        [
            {"id": "X", "task": "t", "relevant": [{"path": "docs/billing.md", "lines": [5, 99]}]},
            {"id": "X", "task": "t", "relevant": [{"path": "nope.md", "lines": [1, 1]}]},
            {"id": "Y", "task": "t", "kinds": ["bogus"], "relevant": []},
        ],
    )
    with pytest.raises(ValueError) as err:
        load_suite(suite_path)
    message = str(err.value)
    assert "outside docs/billing.md" in message
    assert "duplicate id" in message
    assert "file not found: nope.md" in message
    assert "bogus" in message


def test_gate_evaluation() -> None:
    gate = {
        "gate": "g",
        "criteria": [
            {"id": "C1", "metric": "mean_recall", "op": ">=", "value": 0.8},
            {"id": "C2", "metric": "forbidden_returned", "op": "==", "value": 0},
            {"id": "C3", "metric": "missing_metric", "op": "==", "value": 0},
        ],
    }
    result = evaluate_gate(gate, {"mean_recall": 0.85, "forbidden_returned": 1})
    assert [c["passed"] for c in result["criteria"]] == [True, False, False]
    assert result["passed"] is False


def test_summary_ignores_undefined_values() -> None:
    results = [
        {"category": "a", "recall": 1.0, "precision": None, "package_tokens": {"value": 10},
         "forbidden_returned": [], "unresolved_misses": [], "status_mismatches": []},
        {"category": "a", "recall": 0.5, "precision": 0.5, "package_tokens": {"value": 30},
         "forbidden_returned": [], "unresolved_misses": ["finding"], "status_mismatches": []},
    ]  # fmt: skip
    s = summarize(results, full_corpus_tokens=100)
    assert s["mean_recall"] == 0.75
    assert s["mean_precision"] == 0.5 and s["n_tasks_with_precision"] == 1
    assert s["mean_package_to_corpus_ratio"] == 0.2
    assert s["unresolved_misses"] == 1


def test_committed_suite_and_gate_are_valid() -> None:
    """Catches labels that no longer match the fixture after someone edits it."""
    suite = load_suite(COMMITTED_SUITE)
    assert len(suite.tasks) == 9
    gate = json.loads(COMMITTED_GATE.read_text(encoding="utf-8"))
    assert {c["id"] for c in gate["criteria"]} == {"C1", "C2", "C3", "C4", "C5"}


def test_cli_eval_retrieval(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        ["eval-retrieval", str(COMMITTED_SUITE), "--gate", str(COMMITTED_GATE),
         "--out", str(tmp_path)]
    )  # fmt: skip
    assert code == 0
    out = capsys.readouterr().out
    assert "# Retrieval evaluation: sample_project" in out
    assert "## gate1:" in out
    assert len(list(tmp_path.iterdir())) == 1
