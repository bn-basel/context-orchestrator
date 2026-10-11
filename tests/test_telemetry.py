import json
from pathlib import Path

from context_orchestrator.agent_interface.api import ContextService
from context_orchestrator.models import ContextRequest

TASK = "Cap the overdue fine at the replacement cost (secret-project-name)"


def _events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_jsonl_events_exclude_task_text_by_default(project: Path, tmp_path: Path) -> None:
    with ContextService(project, tmp_path / "state") as svc:
        svc.ingest()
        svc.request(ContextRequest(task=TASK, constraints=["no floats"]))
        svc.request(ContextRequest(task=TASK))
    raw = (tmp_path / "state" / "telemetry.jsonl").read_text(encoding="utf-8")
    assert "secret-project-name" not in raw and "floats" not in raw
    events = _events(tmp_path / "state" / "telemetry.jsonl")
    assert len(events) == 2
    assert events[0]["task_sha256"] == events[1]["task_sha256"]  # groupable without the text
    assert events[0]["schema_version"] == 1
    for key in ("task", "query_terms", "constraints"):
        assert key not in events[0]


def test_task_text_can_be_opted_in(project: Path, tmp_path: Path) -> None:
    with ContextService(project, tmp_path / "state", record_task_text=True) as svc:
        svc.ingest()
        svc.request(ContextRequest(task=TASK))
    event = _events(tmp_path / "state" / "telemetry.jsonl")[0]
    assert event["task"] == TASK
    assert "replacement" in event["query_terms"]


def test_metrics_carry_provenance(project: Path, tmp_path: Path) -> None:
    with ContextService(project, tmp_path / "state") as svc:
        svc.ingest()
        svc.request(ContextRequest(task=TASK))
    event = _events(tmp_path / "state" / "telemetry.jsonl")[0]
    assert event["latency_ms"]["kind"] == "measured" and event["latency_ms"]["value"] >= 0
    assert event["package_tokens"]["kind"] == "estimated"
    assert "chars / 4" in event["package_tokens"]["method"]


def test_unwritable_telemetry_does_not_break_requests(project: Path, tmp_path: Path) -> None:
    state = tmp_path / "state"
    with ContextService(project, state) as svc:
        svc.ingest()
        (state / "telemetry.jsonl").mkdir()  # a directory where the file should be
        package = svc.request(ContextRequest(task=TASK))
    assert package.items
