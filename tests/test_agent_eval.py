import json
import subprocess
from pathlib import Path

import pytest

from context_orchestrator.evaluation.agent_eval import (
    MCP_TOOL,
    AgentConfig,
    build_command,
    full_context,
    grade,
    load_rubrics,
    oracle_context,
    parse_stream,
    run_agent_suite,
)
from context_orchestrator.evaluation.retrieval_eval import load_suite

SUITE = Path(__file__).resolve().parents[1] / "benchmarks" / "tasks" / "sample_project.json"

RUBRIC = {
    "checks": [
        {"id": "fn", "any_of": [r"days_overdue"]},
        {"id": "utc", "any_of": [r"\bUTC\b"]},
    ],
    "must_not": [{"id": "float", "any_of": [r"float\s+dollars"]}],
    "example_pass": "Change days_overdue; timestamps are UTC.",
}


def _stream(plan: str, tools: list[str], usage: bool = True) -> str:
    events = [{"type": "system", "subtype": "init", "session_id": "abc", "cwd": "C:/ws/project"}]
    for i, name in enumerate(tools):
        events.append(
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "tool_use", "id": f"t{i}", "name": name, "input": {}}]
                },
            }
        )
        events.append(
            {
                "type": "user",
                "message": {
                    "content": [
                        {"type": "tool_result", "tool_use_id": f"t{i}", "content": "x" * 100}
                    ]
                },
            }
        )
    result = {
        "type": "result",
        "result": plan,
        "num_turns": len(tools) + 1,
        "is_error": False,
        "duration_ms": 1234,
        "session_id": "abc",
    }
    if usage:
        result["modelUsage"] = {
            "claude-haiku": {
                "inputTokens": 10,
                "outputTokens": 50,
                "cacheReadInputTokens": 1000,
                "cacheCreationInputTokens": 500,
                "costUSD": 0.01,
                "costBasis": "list",
            }
        }
    events.append(result)
    return "\n".join(json.dumps(e) for e in events) + "\n"  # fmt: skip


def test_grade() -> None:
    good = grade("Fix days_overdue so partial days count; all timestamps are UTC.", RUBRIC)
    assert good == {"score": 1.0, "passed": ["fn", "utc"], "failed": [],
                    "must_not_violated": [], "success": True}  # fmt: skip
    trap = grade("Store fines as float dollars in days_overdue.", RUBRIC)
    assert trap["score"] == 0.5 and trap["must_not_violated"] == ["float"] and not trap["success"]


def test_parse_stream_counts_service_calls() -> None:
    parsed = parse_stream(_stream("plan", ["Read", MCP_TOOL, MCP_TOOL]).splitlines())
    assert parsed["plan"] == "plan"
    assert parsed["tool_calls"] == ["Read", MCP_TOOL, MCP_TOOL]
    assert parsed["service_calls"] == 2
    assert parsed["service_result_chars"] == 200  # only the service's results


def test_commands_differ_only_by_strategy(tmp_path: Path) -> None:
    config = AgentConfig()
    a = build_command(config, "A", "p", tmp_path / "full.md", None)
    b = build_command(config, "B", "p", tmp_path / "b.md", tmp_path / "mcp.json")
    c = build_command(config, "C", "p", None, None)
    assert "--strict-mcp-config" in a and "--strict-mcp-config" in c
    assert c[c.index("--allowedTools") + 1] == "Read Grep Glob"
    assert b[b.index("--allowedTools") + 1] == f"Read Grep Glob {MCP_TOOL}"
    assert "--mcp-config" in b and "--mcp-config" not in a + c
    assert "--append-system-prompt-file" in a and "--append-system-prompt-file" not in c
    assert b[b.index("--tools") + 1] == "Read,Grep,Glob"  # built-in tools are the same


def test_contexts(tmp_path: Path) -> None:
    suite = load_suite(SUITE)
    full = full_context(suite.project)
    assert "=== db/schema.sql ===" in full and "=== src/shelfwise/loans.py ===" in full
    oracle = oracle_context(suite.project, suite.tasks[0])
    assert "=== docs/known-issues.md:7-11 ===" in oracle
    assert "BUG-12" in oracle and "CREATE TABLE" not in oracle


def test_rubrics_are_validated(tmp_path: Path) -> None:
    suite = load_suite(SUITE)
    bad = {"rubrics": {t.id: RUBRIC for t in suite.tasks}}
    bad["rubrics"]["T01"] = {**RUBRIC, "checks": [{"id": "x", "any_of": ["("]}]}
    path = tmp_path / "r.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="bad regex"):
        load_rubrics(path, suite)


def test_run_agent_suite_with_a_fake_claude(tmp_path: Path) -> None:
    suite = load_suite(SUITE)
    rubrics = tmp_path / "rubrics.json"
    rubrics.write_text(json.dumps({"rubrics": {t.id: RUBRIC for t in suite.tasks}}), "utf-8")
    calls = []

    def fake_runner(cmd, **kwargs):
        calls.append((cmd, kwargs.get("cwd")))
        if cmd[:2] == ["claude", "--version"]:
            return subprocess.CompletedProcess(cmd, 0, b"2.1.292 (Claude Code)\n", b"")
        strategy_b = "--mcp-config" in cmd
        plan = f"Change days_overdue in {kwargs['cwd']}; UTC."
        out = _stream(plan, [MCP_TOOL] if strategy_b else ["Read"], usage=not strategy_b)
        return subprocess.CompletedProcess(cmd, 0, out.encode(), b"")

    run_dir = run_agent_suite(
        suite, rubrics, tmp_path / "out", tmp_path / "work",
        AgentConfig(strategies=("A", "B", "C", "D")), task_ids=["T01", "T02"],
        runner=fake_runner, ctxo_command="ctxo",
    )  # fmt: skip
    records = [
        json.loads(line) for line in (run_dir / "runs.jsonl").read_text("utf-8").splitlines()
    ]
    assert len(records) == 8 and {r["strategy"] for r in records} == {"A", "B", "C", "D"}
    assert all(r["grade"]["success"] for r in records)
    # Local paths never reach stored files.
    assert "<workspace>" in records[0]["plan"] and str(tmp_path) not in records[0]["plan"]
    raw = (run_dir / "raw" / "T01-A-0.jsonl").read_text("utf-8")
    assert '"session_id": "<session>"' in raw
    # Missing usage is unavailable, not zero, and is counted.
    summary = json.loads((run_dir / "run.json").read_text("utf-8"))["summary"]
    assert summary["B"]["usage_unavailable_runs"] == 2
    assert summary["B"]["median_total_input_tokens"] is None
    assert summary["A"]["median_total_input_tokens"] == 1510
    assert summary["B"]["median_service_calls"] == 1
    # Every agent ran in the same read-only project copy.
    assert len({cwd for cmd, cwd in calls if cmd[1] == "-p"}) == 1
    meta = json.loads((run_dir / "run.json").read_text("utf-8"))
    assert meta["claude_code_version"].startswith("2.1.292")
    assert "| A: full context |" in (run_dir / "summary.md").read_text("utf-8")


def test_sanitise_removes_user_name_in_every_form(tmp_path: Path) -> None:
    from context_orchestrator.evaluation.agent_eval import _sanitise

    home = Path.home()
    user = home.name
    text = (
        f'"cwd": "{str(home)}\\x", "memory": "C--Users-{user}-AppData-Local-Temp", '
        f'"detail": "Reading ~\\AppData\\{user}", "session_id": "abc-123"'
    )
    clean = _sanitise(text, {str(home): "<home>"})
    assert user.lower() not in clean.lower()
    assert '"session_id": "<session>"' in clean
