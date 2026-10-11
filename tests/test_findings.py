import io
import json
from pathlib import Path

import pytest

from context_orchestrator.agent_interface.api import ContextService
from context_orchestrator.agent_interface.mcp_server import (
    FINDING_TOOL_NAME,
    McpServer,
    ServerConfig,
    serve,
)
from context_orchestrator.models import InfoKind, Status

CLAIM = "Overdue fines are capped at the item's replacement cost in calculate_fine."
EVIDENCE = "return min(days * DAILY_FINE_CENTS, replacement_cost_cents)"


def _record(service: ContextService, **overrides) -> None:
    args = {
        "claim": CLAIM,
        "path": "src/shelfwise/fines.py",
        "line_start": 12,
        "line_end": 15,
        "evidence": EVIDENCE,
        "agent_id": "test",
    }
    service.record_finding(**{**args, **overrides})


def test_finding_is_served_first_with_its_anchor(service: ContextService) -> None:
    _record(service)
    package = service.request({"task": "why are overdue fines capped at replacement cost"})
    first = package.items[0]
    assert first.kind is InfoKind.FINDING
    assert first.status is Status.UNVERIFIED  # unreviewed findings are never "verified"
    assert first.source.label() == "src/shelfwise/fines.py:12-15"
    assert first.stale is False
    text = package.render_markdown()
    assert CLAIM in text and EVIDENCE in text and "recorded by agent test" in text


def test_unrelated_task_does_not_get_the_finding(service: ContextService) -> None:
    _record(service)
    package = service.request({"task": "catalog search by author"})
    assert all(i.kind is not InfoKind.FINDING for i in package.items)


def test_findings_can_be_switched_off(service: ContextService) -> None:
    _record(service)
    package = service.request({"task": "overdue fines capped", "max_findings": 0})
    assert all(i.kind is not InfoKind.FINDING for i in package.items)


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"evidence": "return max(days, 0)"}, "not a verbatim quote"),
        ({"path": "src/shelfwise/nope.py"}, "no such file"),
        ({"path": "../outside.py"}, "no such file"),
        ({"line_end": 9999}, "lines; cited"),
        ({"line_start": 1, "line_end": 200}, "lines; cited"),
        ({"claim": "short"}, "claim must be"),
    ],
)
def test_bad_anchors_are_rejected(service: ContextService, overrides: dict, reason: str) -> None:
    with pytest.raises(ValueError, match=reason):
        _record(service, **overrides)
    assert service.store.count_findings() == 0


def test_evidence_whitespace_is_normalised(service: ContextService) -> None:
    _record(service, evidence="return   min(days * DAILY_FINE_CENTS,\n replacement_cost_cents)")
    assert service.store.count_findings() == 1


def test_finding_turns_stale_when_its_file_changes(service: ContextService, project: Path) -> None:
    _record(service)
    fines = project / "src" / "shelfwise" / "fines.py"
    fines.write_text(fines.read_text(encoding="utf-8") + "\n# edited\n", encoding="utf-8")
    package = service.request({"task": "why are overdue fines capped at replacement cost"})
    finding = next(i for i in package.items if i.kind is InfoKind.FINDING)
    assert finding.stale is True
    assert "STALE: file changed since it was recorded" in package.render_markdown()


def test_findings_survive_reingest(service: ContextService) -> None:
    _record(service)
    service.ingest()
    assert service.store.count_findings() == 1


def _call(server: McpServer, name: str, arguments: dict) -> dict:
    stdin = io.StringIO(
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        + "\n"
        + json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        + "\n"
    )
    stdout = io.StringIO()
    serve(server, stdin, stdout)
    return {r["id"]: r for r in map(json.loads, stdout.getvalue().splitlines())}


def test_mcp_record_finding_only_when_enabled(service: ContextService) -> None:
    args = {
        "claim": CLAIM,
        "path": "src/shelfwise/fines.py",
        "line_start": 12,
        "line_end": 15,
        "evidence": EVIDENCE,
    }
    off = _call(McpServer(service), FINDING_TOOL_NAME, args)
    assert [t["name"] for t in off[1]["result"]["tools"]] == ["request_context"]
    assert "error" in off[2]

    on = _call(McpServer(service, ServerConfig(memory_write=True)), FINDING_TOOL_NAME, args)
    assert FINDING_TOOL_NAME in [t["name"] for t in on[1]["result"]["tools"]]
    assert on[2]["result"]["isError"] is False
    assert service.store.count_findings() == 1

    bad = _call(
        McpServer(service, ServerConfig(memory_write=True)),
        FINDING_TOOL_NAME,
        {**args, "evidence": "invented"},
    )
    assert bad[2]["result"]["isError"] is True
    assert "Not recorded" in bad[2]["result"]["content"][0]["text"]
