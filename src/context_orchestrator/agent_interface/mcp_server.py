"""A minimal MCP server exposing the context service as one tool.

MCP (Model Context Protocol) is how Claude Code and other agent hosts call
external tools. This implements the small part of it a tool server needs:
newline-delimited JSON-RPC 2.0 over stdin/stdout with ``initialize``,
``tools/list``, ``tools/call`` and ``ping``. Standard library only.

Run it with ``ctxo mcp <project> [--retrieval hybrid --hops 2 ...]`` and point
the host at that command, e.g. a Claude Code ``--mcp-config`` file:

    {"mcpServers": {"ctxo": {"command": "ctxo", "args": ["mcp", "path/to/project"]}}}

stdout carries only protocol messages; logs go to stderr.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from typing import IO, Any

from context_orchestrator import __version__
from context_orchestrator.agent_interface.api import ContextService
from context_orchestrator.models import ContextRequest, InfoKind

log = logging.getLogger(__name__)

TOOL_NAME = "request_context"
DEFAULT_PROTOCOL_VERSION = "2025-06-18"

TOOL = {
    "name": TOOL_NAME,
    "description": (
        "Ask the project's context service for knowledge relevant to a task: architecture "
        "decisions, schemas, conventions, constraints, known issues, findings, code and tests. "
        "Returns verbatim excerpts with file paths and line ranges, each labelled with how far "
        "it can be trusted (verified, observed in source, unverified, assumption), plus what "
        "could not be found. Ask specific questions; call again with follow-up questions "
        "(e.g. about a function or table an earlier answer named)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "What you are trying to do or find out, in plain words.",
            },
            "kinds": {
                "type": "array",
                "items": {"type": "string", "enum": [k.value for k in InfoKind]},
                "description": "Kinds of information wanted (default: any).",
            },
            "constraints": {"type": "array", "items": {"type": "string"}},
            "max_tokens": {
                "type": "integer",
                "minimum": 200,
                "maximum": 16000,
                "description": "Size limit for the answer (default 4000).",
            },
        },
        "required": ["task"],
    },
}


@dataclass(slots=True)
class ServerConfig:
    max_tokens: int = 4000
    per_kind_limit: int = 3
    hops: int = 1
    detail: str = "full"


class McpServer:
    def __init__(self, service: ContextService, config: ServerConfig | None = None) -> None:
        self.service = service
        self.config = config or ServerConfig()
        self.calls = 0

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """Handle one JSON-RPC message; returns the response, or None for notifications."""
        method = message.get("method")
        msg_id = message.get("id")
        if msg_id is None:  # notification (e.g. notifications/initialized): no reply
            return None
        try:
            result = self._dispatch(method, message.get("params") or {})
        except _RpcError as exc:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": exc.code, "message": str(exc)},
            }
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    def _dispatch(self, method: str | None, params: dict[str, Any]) -> dict[str, Any]:
        if method == "initialize":
            return {
                "protocolVersion": params.get("protocolVersion", DEFAULT_PROTOCOL_VERSION),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "context-orchestrator", "version": __version__},
            }
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": [TOOL]}
        if method == "tools/call":
            if params.get("name") != TOOL_NAME:
                raise _RpcError(-32602, f"unknown tool {params.get('name')!r}")
            return self._call(params.get("arguments") or {})
        raise _RpcError(-32601, f"method not found: {method}")

    def _call(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Tool errors are returned as results with isError, so the agent can read them."""
        self.calls += 1
        try:
            request = ContextRequest.from_dict(
                {
                    "task": arguments.get("task", ""),
                    "kinds": arguments.get("kinds") or [],
                    "constraints": arguments.get("constraints") or [],
                    "max_tokens": int(arguments.get("max_tokens") or self.config.max_tokens),
                    "per_kind_limit": self.config.per_kind_limit,
                    "hops": self.config.hops,
                    "detail": self.config.detail,
                    "agent_id": "mcp",
                }
            )
            package = self.service.request(request)
        except (ValueError, RuntimeError) as exc:
            return {"content": [{"type": "text", "text": f"Error: {exc}"}], "isError": True}
        return {"content": [{"type": "text", "text": package.render_markdown()}], "isError": False}


class _RpcError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def serve(server: McpServer, stdin: IO[str], stdout: IO[str]) -> None:
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            response: dict[str, Any] | None = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "parse error"},
            }
        else:
            response = server.handle(message)
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            stdout.flush()


def run_stdio(server: McpServer) -> None:
    stdin = open(sys.stdin.fileno(), encoding="utf-8", closefd=False)  # noqa: SIM115
    stdout = open(sys.stdout.fileno(), "w", encoding="utf-8", newline="\n", closefd=False)  # noqa: SIM115
    serve(server, stdin, stdout)
