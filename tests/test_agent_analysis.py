import json
from pathlib import Path

from context_orchestrator.evaluation.agent_analysis import analyse, write_analysis


def _run(task: str, strategy: str, rep: int, score: float, tokens: int | None, service: int = 0):
    return {
        "task_id": task, "strategy": strategy, "repetition": rep, "error": None,
        "grade": {"score": score, "success": score == 1.0},
        "usage": {"total_input_tokens": {"value": tokens},
                  "api_equivalent_cost_usd": {"value": None if tokens is None else tokens / 1e6}},
        "service_calls": service,
        "tool_calls": ["Read"] * 3 + ["mcp__ctxo__request_context"] * service,
    }  # fmt: skip


def _write(tmp_path: Path, runs: list[dict]) -> Path:
    (tmp_path / "runs.jsonl").write_text("\n".join(json.dumps(r) for r in runs) + "\n", "utf-8")
    return tmp_path


def test_paired_analysis_on_known_data(tmp_path: Path) -> None:
    runs = []
    for i in range(10):
        task = f"T{i}"
        base = 0.4 + 0.05 * i  # tasks differ in difficulty
        for rep in range(3):
            runs.append(_run(task, "C", rep, base, 200_000))
            runs.append(_run(task, "B", rep, base + 0.1, 100_000, service=1))  # always better
            runs.append(_run(task, "A", rep, base, 400_000))  # same quality, 2x tokens
    analysis = analyse(_write(tmp_path, runs))
    b = analysis["comparisons"]["B vs C"]
    assert abs(b["score"]["mean_difference"] - 0.1) < 1e-9
    low, high = b["score"]["ci95"]
    assert low > 0  # a consistent improvement is detected
    assert abs(b["input_tokens_ratio"]["ratio"] - 0.5) < 1e-9
    a = analysis["comparisons"]["A vs C"]
    assert a["score"]["ci95"] == (0.0, 0.0)
    assert abs(a["input_tokens_ratio"]["ratio"] - 2.0) < 1e-9
    assert analysis["service_use"]["B"]["runs_using_service"] == 30
    assert analysis["service_use"]["C"]["runs_using_service"] == 0


def test_failed_and_superseded_attempts_are_handled(tmp_path: Path) -> None:
    runs = [
        _run("T1", "C", 0, 0.5, 100),
        _run("T1", "B", 0, 0.5, 100),
        {**_run("T1", "B", 1, 0.0, None), "error": "usage limit"},  # failed: excluded
        _run("T2", "C", 0, 0.5, 100),
        _run("T2", "B", 0, 0.0, 100),
        _run("T2", "B", 0, 1.0, 100),  # a later attempt replaces the earlier one
    ]
    analysis = analyse(_write(tmp_path, runs))
    assert analysis["runs_analysed"] == 4
    assert analysis["comparisons"]["B vs C"]["score"]["mean_difference"] == 0.25
    text = write_analysis(tmp_path).read_text("utf-8")
    assert "| B vs C |" in text and (tmp_path / "analysis.json").exists()
