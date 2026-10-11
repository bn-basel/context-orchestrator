"""End-to-end vertical slice: knowledge base -> request -> package -> telemetry."""

from pathlib import Path

import pytest

from context_orchestrator.agent_interface.api import ContextService
from context_orchestrator.models import ContextRequest, InfoKind, MetricKind, Status
from context_orchestrator.telemetry.events import MemoryTelemetry

BUG12_TASK = "Fix BUG-12 so a book returned one hour late is not charged a full day's fine"


def test_full_flow_returns_sourced_context(
    service: ContextService, project: Path, telemetry: MemoryTelemetry
) -> None:
    package = service.request(
        ContextRequest(
            task=BUG12_TASK,
            kinds=[InfoKind.KNOWN_ISSUE, InfoKind.CODE, InfoKind.TEST, InfoKind.FINDING],
            agent_id="bugfix-agent",
        )
    )

    # The most relevant evidence is present...
    labels = [i.source.label() for i in package.items]
    assert labels[0].startswith("docs/known-issues.md")
    headings = [i.heading for i in package.items]
    assert "src/shelfwise/loans.py::days_overdue" in headings
    assert any(i.kind is InfoKind.TEST for i in package.items)

    # ...every item traces back to the exact lines of an unchanged file...
    for item in package.items:
        lines = (project / item.source.path).read_text(encoding="utf-8").splitlines()
        assert item.text == "\n".join(lines[item.source.line_start - 1 : item.source.line_end])
        assert item.stale is False
        assert item.matched_terms  # every item is explained by matched terms

    # ...and the gap is reported instead of being filled in.
    assert len(package.unresolved) == 1
    assert package.unresolved[0].startswith("No finding information matched")

    # One telemetry event was recorded for the request.
    assert len(telemetry.events) == 1
    event = telemetry.events[0]
    assert event["request_id"] == package.request_id
    assert event["agent_id"] == "bugfix-agent"
    assert event["items_returned"] == len(package.items)
    assert event["latency_ms"]["kind"] == MetricKind.MEASURED
    assert event["package_tokens"]["kind"] == MetricKind.ESTIMATED


def test_token_budget_is_respected(service: ContextService) -> None:
    package = service.request(ContextRequest(task=BUG12_TASK, max_tokens=150))
    assert sum(i.estimated_tokens for i in package.items) <= 150
    assert any(o.reason.startswith("token budget") for o in package.omitted)


def test_budget_round_robin_covers_each_requested_kind(service: ContextService) -> None:
    package = service.request(
        ContextRequest(
            task="fine cents calculation",
            kinds=[InfoKind.DECISION, InfoKind.SCHEMA, InfoKind.CODE],
            max_tokens=400,
        )
    )
    assert {i.kind for i in package.items} == {InfoKind.DECISION, InfoKind.SCHEMA, InfoKind.CODE}


def test_superseded_decisions_are_omitted_with_a_reason(service: ContextService) -> None:
    request = ContextRequest(
        task="store fines as float dollars or integer cents", kinds=[InfoKind.DECISION]
    )
    package = service.request(request)
    assert not any(i.status is Status.SUPERSEDED for i in package.items)
    assert any(o.reason == "superseded" and "0002" in o.source.path for o in package.omitted)
    assert any("0004" in i.source.path for i in package.items)


def test_assumptions_are_flagged(service: ContextService) -> None:
    package = service.request(
        ContextRequest(task="maximum active loans per member limit", kinds=[InfoKind.CONSTRAINT])
    )
    assumption = [i for i in package.items if i.status is Status.ASSUMPTION]
    assert assumption, "the loan-limit assumption should be retrieved"
    assert any("assumption, not verified" in n for n in package.notes)


def test_changed_source_is_marked_stale(service: ContextService, project: Path) -> None:
    loans = project / "src" / "shelfwise" / "loans.py"
    loans.write_text(loans.read_text(encoding="utf-8") + "\n# edited\n", encoding="utf-8")
    package = service.request(ContextRequest(task="days overdue", kinds=[InfoKind.CODE]))
    stale = [i for i in package.items if i.source.path == "src/shelfwise/loans.py"]
    assert stale and all(i.stale for i in stale)
    assert any("changed since ingestion" in n for n in package.notes)


def test_task_without_search_terms_is_unresolved(service: ContextService) -> None:
    package = service.request(ContextRequest(task="please fix this"))
    assert package.items == []
    assert "no searchable terms" in package.unresolved[0]


def test_request_validation() -> None:
    with pytest.raises(ValueError):
        ContextRequest.from_dict({"task": "   "})
    with pytest.raises(ValueError):
        ContextRequest.from_dict({"task": "x", "kinds": ["not-a-kind"]})


def test_empty_knowledge_base_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "proj").mkdir()
    with (
        ContextService.without_telemetry(tmp_path / "proj", tmp_path / "state") as svc,
        pytest.raises(RuntimeError, match="Run ingest first"),
    ):
        svc.request({"task": "anything"})


def test_markdown_rendering_includes_sources_and_unresolved(service: ContextService) -> None:
    package = service.request(
        ContextRequest(task=BUG12_TASK, kinds=[InfoKind.KNOWN_ISSUE, InfoKind.FINDING])
    )
    text = package.render_markdown()
    assert "(docs/known-issues.md:" in text
    assert "## Unresolved" in text
