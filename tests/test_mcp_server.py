import io
import json
import os
import subprocess
import sys
from pathlib import Path

from context_orchestrator.agent_interface.api import ContextService
from context_orchestrator.agent_interface.mcp_server import TOOL_NAME, McpServer, serve


def _rpc(server: McpServer, *messages: dict) -> list[dict]:
    stdin = io.StringIO("".join(json.dumps(m) + "\n" for m in messages) + "not json\n")
    stdout = io.StringIO()
    serve(server, stdin, stdout)
    return [json.loads(line) for line in stdout.getvalue().splitlines()]


def test_protocol_round_trip(service: ContextService) -> None:
    server = McpServer(service)
    responses = _rpc(
        server,
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-03-26", "capabilities": {}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": TOOL_NAME,
                    "arguments": {"task": "fine cap replacement cost", "kinds": ["constraint"]}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
         "params": {"name": TOOL_NAME, "arguments": {"task": "x", "kinds": ["nonsense"]}}},
        {"jsonrpc": "2.0", "id": 5, "method": "nope"},
    )  # fmt: skip
    by_id = {r["id"]: r for r in responses}
    assert by_id[1]["result"]["protocolVersion"] == "2025-03-26"  # echoes the client
    assert by_id[2]["result"]["tools"][0]["name"] == TOOL_NAME
    text = by_id[3]["result"]["content"][0]["text"]
    assert by_id[3]["result"]["isError"] is False and "docs/constraints.md" in text
    assert by_id[4]["result"]["isError"] is True  # bad arguments are a tool error, not a crash
    assert by_id[5]["error"]["code"] == -32601
    assert by_id[None]["error"]["code"] == -32700  # the unparseable line
    assert len(responses) == 6  # the notification got no reply
    assert server.calls == 2


def test_stdio_subprocess(project: Path, tmp_path: Path) -> None:
    """The real `ctxo mcp` process: protocol on stdout only, UTF-8, one line per reply."""
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": TOOL_NAME, "arguments": {"task": "money integer cents"}}},
    ]  # fmt: skip
    proc = subprocess.run(
        [sys.executable, "-m", "context_orchestrator.agent_interface.cli", "mcp", str(project),
         "--state-dir", str(tmp_path / "state")],
        input="".join(json.dumps(m) + "\n" for m in messages).encode("utf-8"),
        capture_output=True,
        timeout=60,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )  # fmt: skip
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    lines = proc.stdout.decode("utf-8").splitlines()
    assert [json.loads(line)["id"] for line in lines] == [1, 2]
    assert "ADR 0004" in json.loads(lines[1])["result"]["content"][0]["text"]
