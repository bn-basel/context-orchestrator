from pathlib import Path

from context_orchestrator.evaluation.retrieval_eval import Label
from context_orchestrator.evaluation.trace_analysis import SERVICE_TOOL, Call, RunTrace
from context_orchestrator.evaluation.what_if import (
    STUB_CHARS,
    complete_first_answer,
    fit_cost_model,
    prune_after,
    whole_files,
)


def _trace(calls: list[Call]) -> RunTrace:
    for i, c in enumerate(calls):
        c.carried_chars = c.result_chars * (len(calls) - i)
    return RunTrace("T", "B2", 0, 1.0, calls, [r for c in calls for r in c.served])


def test_prune_after_replaces_old_results_with_stubs() -> None:
    calls = [
        Call("Read", "a.py", None, 1000),
        Call("Grep", None, None, 50),
        Call("Read", "b.py", None, 500),
    ]
    trace = _trace(calls)
    # Only the first result is still carried after 1 further call: (1000-80) x (3-1) removed.
    assert prune_after(trace, 1) == -(1000 - STUB_CHARS) * (3 - 1)
    assert prune_after(trace, 10) == 0


def test_whole_files_and_complete_first_answer(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "\n".join("x" * 9 for _ in range(10)) + "\n", "utf-8"
    )  # 100 chars
    service = Call(SERVICE_TOOL, None, None, 300, served=[("a.py", 1, 2)])
    reread = Call("Read", "a.py", None, 100)
    reread.klass = "served"
    trace = _trace([service, Call("Grep", None, None, 10), reread])
    # Whole file instead of 2 lines: +80 chars carried for 3 calls; the later re-read disappears.
    assert whole_files(trace, tmp_path, 1_000, {}) == 80 * 3 - 100 * 1
    assert whole_files(trace, tmp_path, 50, {}) == 0  # file too large for the threshold
    reread.klass = "needed_missed"
    labels = [Label("a.py", 5, 6)]  # 20 chars
    assert complete_first_answer(trace, labels, tmp_path, {}) == 20 * 3 - 100


def test_cost_model_recovers_known_coefficients() -> None:
    traces, tokens = [], {}
    for i, (n, carried) in enumerate([(2, 1000), (5, 5000), (9, 2000), (4, 9000)]):
        calls = [Call("Grep", None, None, 0) for _ in range(n - 1)]
        calls[0].carried_chars = carried
        trace = RunTrace(f"T{i}", "B2", 0, 1.0, calls, [])
        traces.append(trace)
        tokens[(f"T{i}", "B2", 0)] = 3000 * n + 0.5 * carried
    model = fit_cost_model(traces, tokens)
    assert abs(model["per_call_tokens"] - 3000) < 1e-6
    assert abs(model["tokens_per_carried_char"] - 0.5) < 1e-9
