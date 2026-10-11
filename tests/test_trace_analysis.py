import json

from context_orchestrator.evaluation.retrieval_eval import Label
from context_orchestrator.evaluation.trace_analysis import (
    SERVICE_TOOL,
    RunTrace,
    classify,
    label_coverage,
    parse_trace,
)


def _use(i: int, name: str, inp: dict) -> str:
    block = {"type": "tool_use", "id": f"t{i}", "name": name, "input": inp}
    return json.dumps({"type": "assistant", "message": {"content": [block]}})


def _result(i: int, content) -> str:
    block = {"type": "tool_result", "tool_use_id": f"t{i}", "content": content}
    return json.dumps({"type": "user", "message": {"content": [block]}})


SERVICE_ANSWER = [{"type": "text", "text": (
    "# Context package for: x\n\n"
    "## Known issues > HP-1  (docs/issues.md:5-9)\n_[known_issue, verified]_\n\ntext\n\n"
    "## src/app/a.py::f  (src/app/a.py:10-20)\n_[code, observed]_\n\ndef f(): ...\n"
)}]  # fmt: skip

A_PY = "<workspace>\\project\\src\\app\\a.py"

STREAM = "\n".join([
    _use(0, "Read", {"file_path": "<workspace>\\project\\src\\app\\early.py"}),  # before service
    _result(0, "x" * 100),
    _use(1, SERVICE_TOOL, {"task": "x"}),
    _result(1, SERVICE_ANSWER),
    _use(2, "Read", {"file_path": A_PY, "offset": 12, "limit": 5}),
    _result(2, "y" * 50),
    _use(3, "Read", {"file_path": "<workspace>/project/tests/test_a.py"}),
    _result(3, "z" * 30),
    _use(4, "Read", {"file_path": A_PY, "offset": 40, "limit": 5}),
    _result(4, "w" * 10),
    _use(5, "Grep", {"pattern": "f"}),
    _result(5, "a.py"),
])  # fmt: skip

LABELS = [
    Label("src/app/a.py", 10, 20),
    Label("tests/test_a.py", 1, 8),  # not served: the agent finds it itself
    Label("db/schema.sql", 1, 5),  # never seen
]


def test_parse_and_classify() -> None:
    calls, served = parse_trace(STREAM)
    assert [c.tool for c in calls] == ["Read", SERVICE_TOOL, "Read", "Read", "Read", "Grep"]
    assert served == [("docs/issues.md", 5, 9), ("src/app/a.py", 10, 20)]
    assert calls[2].path == "src/app/a.py" and calls[2].span == (12, 16)
    # Carried = size x calls from here on (6 calls in total).
    assert calls[0].carried_chars == 100 * 6 and calls[2].carried_chars == 50 * 4
    trace = RunTrace("T", "B2", 0, 0.8, calls, served)
    classify(trace, LABELS)
    assert [c.klass for c in calls if c.tool == "Read"] == [
        "unrelated",  # read before the service answered
        "served",  # inside a returned range
        "needed_missed",  # labelled, not returned
        "same_file",  # another part of a returned file
    ]
    assert label_coverage(trace, LABELS) == {"served": 1, "read_only": 1, "unseen": 1}
