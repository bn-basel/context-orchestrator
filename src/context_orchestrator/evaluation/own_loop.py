"""Phase 4: our own agent loop, so the context it carries can be edited between steps.

Claude Code decides for itself what stays in the agent's context, so the
phase 3 estimate (pruning old tool output could save a third to a half of
input tokens) cannot be tested through it. This module is a small agent loop
of our own: the same kind of read-only file tools (read_file, grep, glob),
optionally the context service (request_context) and the memory write path
(record_finding), and a pruning rule applied to the message list before each
model call. It talks to the Anthropic Messages API format, by default through
OpenRouter's Anthropic-compatible endpoint with an ``OPENROUTER_API_KEY``.

Arms (compare only arms of this loop with each other; the loop is not Claude
Code, so its numbers are not comparable with phase 2):

* ``L``   file tools only.
* ``LP``  as L, with pruning of old tool results.
* ``S``   as L plus request_context, told to use it first (like phase 2's B2).
* ``SP``  as S, with pruning.
* ``SM``  as S plus record_finding, told to record findings for later tasks.
  The memory experiment runs a parent task with SM, then the follow-up task
  with SM on the memory the parent left (``SM``) or on an empty one (``SM0``),
  so both follow-up arms have identical tools and instructions.

Pruning (``PrunePolicy``) mirrors the Claude API's ``clear_tool_uses`` edit:
when the uncleared tool results exceed a trigger, every one except the most
recent few is replaced by a one-line stub naming the call, so the agent can
repeat it if it needs the text again. Clearing in batches, not every step,
keeps prompt-cache rewrites rare: editing an early message invalidates the
cache from that point on.

Every number is labelled: token counts are measured (reported by the API);
cost is estimated from list prices, and measured when OpenRouter reports the
charged amount for the call. The API key is read from the environment or the
repository's git-ignored ``.env`` file, and never printed or written anywhere.
"""

from __future__ import annotations

import fnmatch
import gzip
import hashlib
import json
import math
import os
import random
import re
import shutil
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from context_orchestrator.agent_interface.api import ContextService
from context_orchestrator.agent_interface.mcp_server import FINDING_TOOL, record_finding_text
from context_orchestrator.evaluation.agent_eval import PROMPT, SYSTEM_B2, grade, load_rubrics
from context_orchestrator.evaluation.retrieval_eval import EvalTask, TaskSuite, _git_state
from context_orchestrator.models import ContextRequest, InfoKind
from context_orchestrator.tokens import estimate_tokens

OPENROUTER_BASE_URL = "https://openrouter.ai/api"
KEY_ENV = "OPENROUTER_API_KEY"
ENV_FILE = Path(__file__).resolve().parents[3] / ".env"  # repository root; git-ignored
DEFAULT_MODEL = "anthropic/claude-haiku-5.5"
# USD per million tokens: input, output, cache write (5-minute), cache read, by prompt size.
# A call whose prompt (input + cache read + cache write) exceeds the threshold is billed
# entirely at the second card. Anthropic list prices as OpenRouter publishes them
# (openrouter.ai/api/v1/models, 2026-10-11); used only for estimates.
PRICES = {
    "anthropic/claude-haiku-5.5": [
        (100_000, (0.10, 0.50, 0.125, 0.01)),
        (None, (0.50, 2.50, 0.625, 0.05)),
    ],
}
EFFORT = "medium"  # Claude Haiku 5.5's default, stated explicitly
THINKING_TYPES = ("thinking", "redacted_thinking")
PROVIDER = {"only": ["anthropic"], "allow_fallbacks": False}

ARMS = ("L", "LP", "LC", "LE", "S", "SE", "SP", "SM", "SM0", "TR", "TU", "T0", "X")
SERVICE_ARMS = ("S", "SE", "SP", "SM", "SM0", "TR", "TU", "T0", "X")
MEMORY_ARMS = ("SM", "SM0")
PRUNE_ARMS = ("LP", "SP")
COMPACT_READ_ARMS = ("LC",)
TRUST_ARMS = ("TR", "TU", "T0", "X")
TRUSTING_ARMS = ("TR", "X")  # told to rely on verified findings
# X combines the three levers that worked: service first, trusted reviewed memory, effort low.
ARM_EFFORT = {"LE": "low", "SE": "low", "X": "low"}  # every other arm uses LoopConfig.effort

READ_LIMIT_LINES = 2000
COMPACT_READ_LINES = 150  # LC: whole-file reads of longer files return an outline
OUTLINE_HEAD_LINES = 20
MAX_LINE_CHARS = 2000
MAX_RESULT_CHARS = 60_000
MAX_GREP_MATCHES = 100
MAX_GLOB_PATHS = 200
SKIP_DIRS = {".git", "__pycache__", ".ctxo", ".pytest_cache", ".venv"}

SYSTEM_LOOP = (
    "You are working in a read-only copy of a software project. Use the tools to look at "
    "its files; paths are relative to the project root. Be efficient: search before "
    "reading, and read only what you need. When you have enough information, reply with "
    "your final answer as plain text, without calling a tool."
)
SYSTEM_MEMORY = (
    " A colleague will work on a related task in this project next week. Before your final "
    "answer, use record_finding to save the 3-6 findings they would most need (where the "
    "relevant behaviour lives, rules and decisions that constrain it, traps), each anchored "
    "to the lines that show it. Findings from earlier tasks may appear in request_context "
    "answers: they are unreviewed, so check anything you rely on heavily."
)
# Trust experiment: TU and T0 get the cautious line, TR the trusting one; nothing else differs.
SYSTEM_FINDINGS_CAUTIOUS = (
    " Findings from earlier tasks may appear in request_context answers: they are "
    "unreviewed, so check anything you rely on heavily."
)
SYSTEM_FINDINGS_TRUSTED = (
    " Findings from earlier tasks may appear in request_context answers. Those labelled "
    "verified were checked by a reviewer against the lines they cite: rely on them, and open "
    "a file only for details they don't cover."
)

TOOLS = [
    {
        "name": "read_file",
        "description": "Read a text file. Returns numbered lines. Use offset and limit to "
        "read part of a long file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "offset": {"type": "integer", "minimum": 1, "description": "first line"},
                "limit": {"type": "integer", "minimum": 1, "description": "number of lines"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "grep",
        "description": "Search file contents with a regular expression. Returns "
        "path:line: text for each match (at most 100).",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string", "description": "file or directory to search"},
                "glob": {"type": "string", "description": "only files matching, e.g. *.py"},
                "ignore_case": {"type": "boolean"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "glob",
        "description": "List files matching a glob pattern such as src/**/*.py.",
        "input_schema": {
            "type": "object",
            "properties": {"pattern": {"type": "string"}},
            "required": ["pattern"],
        },
    },
]
SERVICE_TOOL = {
    "name": "request_context",
    "description": (
        "Ask the project's context service for knowledge relevant to a task: decisions, "
        "schemas, conventions, constraints, known issues, findings, code and tests. Returns "
        "verbatim excerpts with file paths, line ranges and trust labels, plus what could "
        "not be found. Call again with follow-up questions."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "task": {"type": "string"},
            "kinds": {
                "type": "array",
                "items": {"type": "string", "enum": [k.value for k in InfoKind]},
            },
        },
        "required": ["task"],
    },
}
MEMORY_TOOL = {
    "name": FINDING_TOOL["name"],
    "description": FINDING_TOOL["description"],
    "input_schema": FINDING_TOOL["inputSchema"],
}


# -- tools ---------------------------------------------------------------------------------


class LocalTools:
    """Read-only tools confined to one project directory."""

    def __init__(self, project: Path, service: ContextService | None = None,
                 service_hops: int = 2, agent_id: str = "loop",
                 compact_reads: bool = False) -> None:  # fmt: skip
        self.project = project.resolve()
        self.service = service
        self.service_hops = service_hops
        self.agent_id = agent_id
        self.compact_reads = compact_reads

    def run(self, name: str, args: dict[str, Any]) -> tuple[str, bool]:
        """Returns (result text, is_error). Tool errors go back to the agent as text."""
        try:
            if name == "read_file":
                return self._read(args), False
            if name == "grep":
                return self._grep(args), False
            if name == "glob":
                return self._glob(args), False
            if name == "request_context" and self.service is not None:
                return self._request(args), False
            if name == "record_finding" and self.service is not None:
                return record_finding_text(self.service, args, self.agent_id)
            return f"Unknown tool {name!r}.", True
        except (ValueError, OSError, re.error, KeyError, TypeError) as exc:
            return f"Error: {exc}", True

    def _resolve(self, path: str) -> Path:
        target = (self.project / path.replace("\\", "/")).resolve()
        if not target.is_relative_to(self.project):
            raise ValueError(f"{path} is outside the project")
        return target

    def _files(self, root: Path) -> list[Path]:
        if root.is_file():
            return [root]
        return sorted(
            p for p in root.rglob("*")
            if p.is_file() and not SKIP_DIRS.intersection(p.relative_to(self.project).parts)
        )  # fmt: skip

    def _rel(self, path: Path) -> str:
        return path.relative_to(self.project).as_posix()

    def _read(self, args: dict[str, Any]) -> str:
        path = self._resolve(str(args["path"]))
        if not path.is_file():
            raise ValueError(f"no such file: {args['path']}")
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        whole_file = not args.get("offset") and not args.get("limit")
        if self.compact_reads and whole_file and len(lines) > COMPACT_READ_LINES:
            return _outline(self._rel(path), lines)
        start = max(1, int(args.get("offset") or 1))
        limit = max(1, int(args.get("limit") or READ_LIMIT_LINES))
        shown = lines[start - 1 : start - 1 + limit]
        out = "\n".join(f"{start + i:>6}\t{line[:MAX_LINE_CHARS]}" for i, line in enumerate(shown))
        end = start + len(shown) - 1
        if end < len(lines):
            out += f"\n... ({len(lines)} lines in total; showing {start}-{end})"
        return _cap(out or "(empty file)")

    def _grep(self, args: dict[str, Any]) -> str:
        flags = re.IGNORECASE if args.get("ignore_case") else 0
        regex = re.compile(str(args["pattern"]), flags)
        root = self._resolve(str(args.get("path") or "."))
        pattern = args.get("glob")
        matches = []
        for file in self._files(root):
            rel = self._rel(file)
            if pattern and not any(fnmatch.fnmatch(x, pattern) for x in (rel, file.name)):
                continue
            try:
                text = file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for n, line in enumerate(text.splitlines(), 1):
                if regex.search(line):
                    matches.append(f"{rel}:{n}: {line.strip()[:200]}")
                    if len(matches) >= MAX_GREP_MATCHES:
                        matches.append(f"... (stopped at {MAX_GREP_MATCHES} matches)")
                        return _cap("\n".join(matches))
        return _cap("\n".join(matches) or "No matches.")

    def _glob(self, args: dict[str, Any]) -> str:
        pattern = str(args["pattern"]).replace("\\", "/").lstrip("/")
        paths = [
            self._rel(p) for p in sorted(self.project.glob(pattern))
            if p.is_file() and not SKIP_DIRS.intersection(p.relative_to(self.project).parts)
        ]  # fmt: skip
        if len(paths) > MAX_GLOB_PATHS:
            paths = paths[:MAX_GLOB_PATHS] + [f"... ({len(paths)} files in total)"]
        return "\n".join(paths) or "No files matched."

    def _request(self, args: dict[str, Any]) -> str:
        assert self.service is not None
        request = ContextRequest.from_dict(
            {"task": args.get("task", ""), "kinds": args.get("kinds") or [],
             "hops": self.service_hops, "agent_id": self.agent_id}
        )  # fmt: skip
        return self.service.request(request).render_markdown()


# Lines that name a part of a file: Python definitions, Markdown headings, SQL statements.
_OUTLINE = re.compile(
    r"^\s*(?:async\s+def|def|class)\s+\w+"
    r"|^#{1,6}\s+\S"
    r"|^\s*(?:CREATE|ALTER|DROP)\s+\w+|^\s*INSERT\s+INTO\s",
    re.IGNORECASE,
)


def _outline(rel: str, lines: list[str]) -> str:
    """A long file's opening lines plus every line that starts a definition or section."""
    head = [f"{n:>6}\t{line[:200]}" for n, line in enumerate(lines[:OUTLINE_HEAD_LINES], 1)]
    marks = [
        f"{n:>6}\t{line.rstrip()[:160]}"
        for n, line in enumerate(lines, 1)
        if n > OUTLINE_HEAD_LINES and _OUTLINE.match(line)
    ]
    return _cap(
        f"{rel} has {len(lines)} lines, so only its outline is shown: the first "
        f"{OUTLINE_HEAD_LINES} lines, then the line where each definition or section starts. "
        "Call read_file with offset and limit to read the part you need.\n"
        + "\n".join(head)
        + "\n...\n"
        + ("\n".join(marks) or "(no definitions or headings found)")
    )


def _cap(text: str) -> str:
    if len(text) <= MAX_RESULT_CHARS:
        return text
    return text[:MAX_RESULT_CHARS] + f"\n... (output truncated at {MAX_RESULT_CHARS} characters)"


# -- pruning -------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PrunePolicy:
    trigger_tokens: int = 12_000  # act when uncleared tool results exceed this (estimated)
    keep: int = 3  # the most recent tool results are never cleared
    min_clear_tokens: int = 4_000  # clear only if at least this much can go


def _stub(name: str, args: dict[str, Any]) -> str:
    shown = json.dumps(args, ensure_ascii=False)
    shown = shown if len(shown) <= 160 else shown[:157] + "..."
    return f"[{name} {shown}: result cleared to save context. Call the tool again if you need it.]"


def prune(messages: list[dict[str, Any]], policy: PrunePolicy) -> dict[str, int] | None:
    """Clear old tool results in place. Returns what was cleared, or None if nothing was."""
    calls: dict[str, tuple[str, dict[str, Any]]] = {}
    results: list[tuple[int, dict[str, Any]]] = []  # (message index, block)
    for i, message in enumerate(messages):
        for block in message["content"] if isinstance(message["content"], list) else []:
            if block.get("type") == "tool_use":
                calls[block["id"]] = (block["name"], block.get("input") or {})
            elif block.get("type") == "tool_result" and not block.get("_cleared"):
                results.append((i, block))
    sizes = [estimate_tokens(_result_text(b)) for _, b in results]
    if sum(sizes) <= policy.trigger_tokens:
        return None
    old = results[: max(0, len(results) - policy.keep)]
    freed = sum(sizes[: len(old)])
    if not old or freed < policy.min_clear_tokens:
        return None
    for _, block in old:
        name, args = calls.get(block["tool_use_id"], ("tool", {}))
        block["content"] = _stub(name, args)
        block["_cleared"] = True
    # Newer models (Claude Haiku 5.5 among them) accept a thinking block only while
    # everything sent before it is unchanged, so every thinking block after the first edit
    # is dropped (what the API's drop_block option does). Text and tool calls stay.
    first_edit = old[0][0]
    dropped = 0
    for message in messages[first_edit:]:
        if message["role"] == "assistant":
            kept = [b for b in message["content"] if b.get("type") not in THINKING_TYPES]
            dropped += len(message["content"]) - len(kept)
            message["content"] = kept
    return {
        "cleared_results": len(old),
        "freed_tokens_estimated": freed,
        "thinking_blocks_dropped": dropped,
    }


def _result_text(block: dict[str, Any]) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content
    return "".join(c.get("text", "") for c in content or [] if isinstance(c, dict))


# -- the model call --------------------------------------------------------------------------


@dataclass(slots=True)
class Turn:
    """One model response, as plain data."""

    id: str | None
    stop_reason: str | None
    content: list[dict[str, Any]]
    usage: dict[str, Any]


class Model(Protocol):
    def __call__(self, **kwargs: Any) -> Turn: ...


def read_key() -> str | None:
    """The OpenRouter key: the environment variable if set, else ``KEY=value`` in ENV_FILE.

    ENV_FILE is the repository's ``.env``, which git ignores. Only this one key is read
    from it, and it is never printed or stored.
    """
    if os.environ.get(KEY_ENV):
        return os.environ[KEY_ENV]
    try:
        lines = ENV_FILE.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return None
    for line in lines:
        name, sep, value = line.strip().partition("=")
        if sep and name.strip() == KEY_ENV:
            value = value.strip().strip("\"'")
            return value or None
    return None


def openrouter_model(api_key: str | None = None) -> Model:
    """A Model calling OpenRouter's Anthropic-compatible endpoint with the Anthropic SDK."""
    try:
        import anthropic
    except ImportError as exc:  # optional: uv sync --group loop
        raise RuntimeError("the agent loop needs the Anthropic SDK: uv sync --group loop") from exc
    key = api_key or read_key()
    if not key:
        raise RuntimeError(f"put {KEY_ENV}=<key> in {ENV_FILE} (or set it in the environment)")
    client = anthropic.Anthropic(
        api_key=None, auth_token=key, base_url=OPENROUTER_BASE_URL, max_retries=4
    )

    def call(**kwargs: Any) -> Turn:
        response = client.messages.create(**kwargs, extra_body={"provider": PROVIDER})
        content = []
        for block in response.content:
            if block.type == "text":
                content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                content.append(
                    {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
                )
            elif block.type in THINKING_TYPES:
                # Passed back unmodified with the tool results; the text is usually empty
                # (omitted by default) and only the signature matters.
                content.append(block.model_dump(mode="json", exclude_none=True))
        usage = response.usage.model_dump(mode="json") if response.usage else {}
        return Turn(response.id, response.stop_reason, content, usage)

    return call


def openrouter_generation_cost(generation_id: str, api_key: str | None = None) -> float | None:
    """The charged cost OpenRouter reports for one call, or None if unavailable."""
    key = api_key or read_key()
    if not key or not generation_id:
        return None
    url = f"https://openrouter.ai/api/v1/generation?id={generation_id}"
    for attempt in range(4):
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8")).get("data") or {}
            cost = data.get("total_cost")
            if cost is not None:
                return float(cost)
        except (urllib.error.URLError, json.JSONDecodeError, ValueError):
            pass
        time.sleep(1.5 * (attempt + 1))  # stats can lag the response by a few seconds
    return None


def openrouter_key_status(api_key: str | None = None) -> dict[str, Any] | None:
    """The key's limit and usage so far (USD), as OpenRouter reports them."""
    key = api_key or read_key()
    if not key:
        return None
    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {key}"}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8")).get("data") or {}
    except (urllib.error.URLError, json.JSONDecodeError):
        return None
    return {k: data.get(k) for k in ("limit", "limit_remaining", "usage")}


def estimate_cost(model: str, usage: dict[str, Any]) -> float | None:
    cards = PRICES.get(model)
    if cards is None:
        return None
    prompt = sum(
        usage.get(k) or 0
        for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
    )
    p_in, p_out, p_write, p_read = next(
        prices for limit, prices in cards if limit is None or prompt <= limit
    )
    return (
        (usage.get("input_tokens") or 0) * p_in
        + (usage.get("output_tokens") or 0) * p_out
        + (usage.get("cache_creation_input_tokens") or 0) * p_write
        + (usage.get("cache_read_input_tokens") or 0) * p_read
    ) / 1_000_000


# -- one agent run -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LoopConfig:
    model: str = DEFAULT_MODEL
    max_tokens: int = 16_000  # per response; thinking counts toward it
    effort: str = EFFORT
    max_turns: int = 40
    max_run_usd: float = 0.60  # estimated; stops a runaway run
    max_total_usd: float = 2.00  # estimated, whole experiment; nothing starts beyond it
    prune: PrunePolicy = field(default_factory=PrunePolicy)
    service_hops: int = 2  # keyword retrieval (bm25) with follow-up hops; no Ollama needed
    seed: int = 20261011


def system_prompt(arm: str) -> str:
    text = SYSTEM_LOOP
    if arm in SERVICE_ARMS:
        text += " " + SYSTEM_B2
    if arm in MEMORY_ARMS:
        text += SYSTEM_MEMORY
    if arm in TRUST_ARMS:
        text += SYSTEM_FINDINGS_TRUSTED if arm in TRUSTING_ARMS else SYSTEM_FINDINGS_CAUTIOUS
    return text


def tools_for(arm: str) -> list[dict[str, Any]]:
    tools = list(TOOLS)
    if arm in COMPACT_READ_ARMS:
        read = dict(tools[0])
        read["description"] = (
            f"Read a text file. Returns numbered lines. A file longer than "
            f"{COMPACT_READ_LINES} lines returns an outline (its opening lines and where each "
            "definition or section starts) unless you give offset and limit; then read just "
            "the part you need."
        )
        tools[0] = read
    if arm in SERVICE_ARMS:
        tools.append(SERVICE_TOOL)
    if arm in MEMORY_ARMS:
        tools.append(MEMORY_TOOL)
    return tools


def _with_cache_marks(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A copy whose last block carries the moving cache breakpoint; private keys removed."""
    out = []
    for i, message in enumerate(messages):
        blocks = [{k: v for k, v in b.items() if not k.startswith("_")} for b in message["content"]]
        if i == len(messages) - 1 and blocks:
            blocks[-1] = {**blocks[-1], "cache_control": {"type": "ephemeral"}}
        out.append({"role": message["role"], "content": blocks})
    return out


def run_loop(
    model: Model,
    config: LoopConfig,
    arm: str,
    prompt: str,
    tools: LocalTools,
    spent_before: float = 0.0,
) -> dict[str, Any]:
    """Run one task to its final answer. Returns the transcript and per-call usage."""
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": [{"type": "text", "text": prompt}]}
    ]
    system = [{"type": "text", "text": system_prompt(arm), "cache_control": {"type": "ephemeral"}}]
    calls: list[dict[str, Any]] = []
    tool_calls: list[str] = []
    prune_events: list[dict[str, Any]] = []
    answer, error = "", None
    run_cost = 0.0
    for turn_no in range(config.max_turns):
        if arm in PRUNE_ARMS:
            event = prune(messages, config.prune)
            if event:
                prune_events.append({"before_call": turn_no, **event})
        t0 = time.perf_counter()
        turn = model(
            model=config.model,
            max_tokens=config.max_tokens,
            system=system,
            tools=tools_for(arm),
            messages=_with_cache_marks(messages),
            output_config={"effort": ARM_EFFORT.get(arm, config.effort)},
        )
        cost = estimate_cost(config.model, turn.usage)
        run_cost += cost or 0.0
        charged = turn.usage.get("cost")  # OpenRouter reports its charge in the usage
        calls.append(
            {"id": turn.id, "stop_reason": turn.stop_reason, "usage": turn.usage,
             "estimated_cost_usd": cost,
             "measured_cost_usd": float(charged) if charged is not None else None,
             "wall_ms": round((time.perf_counter() - t0) * 1000)}
        )  # fmt: skip
        messages.append({"role": "assistant", "content": turn.content})
        uses = [b for b in turn.content if b["type"] == "tool_use"]
        if turn.stop_reason == "refusal":
            error = "the model declined the request (stop_reason refusal)"
            break
        if not uses:
            answer = "\n".join(b["text"] for b in turn.content if b["type"] == "text").strip()
            if turn.stop_reason == "max_tokens":
                error = "answer cut off at max_tokens"
            break
        results = []
        for use in uses:
            tool_calls.append(use["name"])
            text, is_error = tools.run(use["name"], use.get("input") or {})
            results.append(
                {"type": "tool_result", "tool_use_id": use["id"], "content": text,
                 "is_error": is_error}
            )  # fmt: skip
        messages.append({"role": "user", "content": results})
        if run_cost > config.max_run_usd:
            error = f"stopped: run reached ~${run_cost:.2f} (limit ${config.max_run_usd})"
            break
        if spent_before + run_cost > config.max_total_usd:
            error = f"stopped: experiment budget ${config.max_total_usd} reached"
            break
    else:
        error = f"stopped: {config.max_turns} turns without a final answer"
    return {
        "answer": answer,
        "error": error,
        "messages": messages,
        "calls": calls,
        "tool_calls": tool_calls,
        "prune_events": prune_events,
    }


def summarise_usage(calls: list[dict[str, Any]], model: str) -> dict[str, dict[str, Any]]:
    def total(key: str) -> int | None:
        values = [c["usage"].get(key) for c in calls]
        if not values or any(v is None for v in values):
            return None
        return int(sum(values))

    def metric(value: float | int | None, kind: str, method: str) -> dict[str, Any]:
        return {"value": value, "kind": kind if value is not None else "unavailable",
                "method": method}  # fmt: skip

    reported = "sum of the API's per-call usage"
    uncached, read, write = (total("input_tokens"), total("cache_read_input_tokens"),
                             total("cache_creation_input_tokens"))  # fmt: skip
    all_input = None if None in (uncached, read, write) else uncached + read + write
    estimated = [c["estimated_cost_usd"] for c in calls]
    measured = [c.get("measured_cost_usd") for c in calls]
    return {
        "input_tokens": metric(uncached, "measured", reported),
        "cache_read_input_tokens": metric(read, "measured", reported),
        "cache_creation_input_tokens": metric(write, "measured", reported),
        "total_input_tokens": metric(all_input, "measured", reported),
        "output_tokens": metric(total("output_tokens"), "measured", reported),
        "estimated_cost_usd": metric(
            None if None in estimated else round(sum(estimated), 6),
            "estimated",
            f"list prices for {model} applied to measured tokens",
        ),  # fmt: skip
        "measured_cost_usd": metric(
            None if not measured or None in measured else round(sum(measured), 6),
            "measured",
            "OpenRouter's reported charge per call",
        ),  # fmt: skip
    }


# -- experiments -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Job:
    task: EvalTask
    arm: str
    rep: int
    rubric: dict[str, Any]
    state: str | None = None  # name of the service state directory to use
    role: str = "task"  # "parent" for memory-building runs
    pair: str | None = None


def plan_prune(suite: TaskSuite, rubrics: dict[str, Any], arms: list[str], reps: int,
               task_ids: list[str] | None, seed: int) -> list[Job]:  # fmt: skip
    tasks = [t for t in suite.tasks if not task_ids or t.id in task_ids]
    jobs = [
        Job(t, a, r, rubrics[t.id], state="base" if a in SERVICE_ARMS else None)
        for r in range(reps) for t in tasks for a in arms
    ]  # fmt: skip
    random.Random(seed).shuffle(jobs)
    return jobs


def plan_memory(followups: TaskSuite, followup_rubrics: dict[str, Any], parents: TaskSuite,
                parent_rubrics: dict[str, Any], after: dict[str, str], reps: int,
                task_ids: list[str] | None, seed: int) -> list[Job]:  # fmt: skip
    """Per follow-up task: parent (SM, own memory) -> follow-up SM on that memory, and the
    follow-up SM0 on an empty memory. Pair order is shuffled; the parent always goes first."""
    by_id = {t.id: t for t in parents.tasks}
    groups = []
    for r in range(reps):
        for task in followups.tasks:
            if task_ids and task.id not in task_ids:
                continue
            parent = by_id[after[task.id]]
            pair = f"{task.id}-{r}"
            fresh = Job(task, "SM0", r, followup_rubrics[task.id], state=f"empty-{pair}",
                        pair=pair)  # fmt: skip
            chain = [
                Job(parent, "SM", r, parent_rubrics[parent.id], state=f"mem-{pair}",
                    role="parent", pair=pair),
                Job(task, "SM", r, followup_rubrics[task.id], state=f"mem-{pair}", pair=pair),
            ]  # fmt: skip
            groups.append([fresh])
            groups.append(chain)
    random.Random(seed).shuffle(groups)
    return [job for group in groups for job in group]


def plan_trust(suite: TaskSuite, rubrics: dict[str, Any], reps: int,
               task_ids: list[str] | None, seed: int) -> list[Job]:  # fmt: skip
    """Follow-up tasks on a memory pre-seeded with reviewed findings: TR (findings marked
    verified, told to rely on them), TU (the same findings unreviewed, told to check) and
    T0 (empty memory, told to check). Run order is shuffled."""
    states = {"TR": "trusted", "TU": "untrusted", "T0": "base"}
    tasks = [t for t in suite.tasks if not task_ids or t.id in task_ids]
    jobs = [
        Job(t, arm, r, rubrics[t.id], state=state)
        for r in range(reps) for t in tasks for arm, state in states.items()
    ]  # fmt: skip
    random.Random(seed).shuffle(jobs)
    return jobs


COMBO_STATES = {"L": None, "S": "base", "SE": "base", "TR": "trusted", "X": "trusted"}


def plan_combo(suite: TaskSuite, rubrics: dict[str, Any], reps: int,
               task_ids: list[str] | None, seed: int,
               arms: tuple[str, ...] = ("L", "S", "X")) -> list[Job]:  # fmt: skip
    """Follow-up tasks with combinations of the working levers: L plain, S context service
    first, SE service first + effort low, TR service first + trusted reviewed memory, X all
    three (service first, trusted memory, effort low). Run order is shuffled."""
    states = {arm: COMBO_STATES[arm] for arm in arms}
    tasks = [t for t in suite.tasks if not task_ids or t.id in task_ids]
    jobs = [
        Job(t, arm, r, rubrics[t.id], state=state)
        for r in range(reps) for t in tasks for arm, state in states.items()
    ]  # fmt: skip
    random.Random(seed).shuffle(jobs)
    return jobs


def trust_seeds(findings_file: Path) -> dict[str, list[dict[str, Any]]]:
    """The confirmed findings of a reviewed-findings file, as seeds for both memories."""
    data = json.loads(findings_file.read_text(encoding="utf-8"))
    confirmed = [f for f in data["findings"] if f["review"] == "confirmed"]
    return {
        "trusted": confirmed,
        "untrusted": [{**f, "review": "unreviewed"} for f in confirmed],
    }


def run_experiment(
    kind: str,
    jobs: list[Job],
    project_src: Path,
    out_dir: Path,
    work_dir: Path,
    config: LoopConfig,
    meta_extra: dict[str, Any],
    model: Model | None = None,
    cost_lookup: Callable[[str], float | None] | None = openrouter_generation_cost,
    key_status: Callable[[], dict[str, Any] | None] | None = openrouter_key_status,
    seeds: dict[str, list[dict[str, Any]]] | None = None,
) -> Path:
    """Run every job in order, writing each result as soon as it finishes.

    ``seeds`` maps a state name to findings to record (and review) in that state
    before its first job: dicts with claim, path, line_start, line_end, evidence,
    agent_id and review.
    """
    model = model or openrouter_model()
    run_id = f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-loop-{kind}"
    run_dir = out_dir / run_id
    (run_dir / "raw").mkdir(parents=True)
    ws = work_dir / run_id
    project = ws / "project"
    shutil.copytree(project_src, project, ignore=shutil.ignore_patterns(*SKIP_DIRS))
    meta = {
        "schema_version": 1,
        "run_id": run_id,
        "experiment": kind,
        "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "git": _git_state(Path(__file__).resolve().parent),
        "config": asdict(config),
        "jobs": [
            {"task": j.task.id, "arm": j.arm, "rep": j.rep, "role": j.role, "pair": j.pair}
            for j in jobs
        ],  # fmt: skip
        "system_prompts": {a: system_prompt(a) for a in ARMS},
        "prompt_template": PROMPT,
        "key_status_before": key_status() if key_status else None,
        **meta_extra,
    }
    _write_json(run_dir / "run.json", meta)
    services: dict[str, ContextService] = {}
    base_state = ws / "state-base"
    if any(j.state for j in jobs):
        with ContextService.without_telemetry(project, base_state) as svc:
            svc.ingest()

    def service_for(name: str) -> ContextService:
        if name not in services:
            path = ws / f"state-{name}"
            if name != "base" and not path.exists():
                shutil.copytree(base_state, path)
            services[name] = svc = ContextService.without_telemetry(project, path)
            for seed in (seeds or {}).get(name, []):
                finding = svc.record_finding(
                    seed["claim"], seed["path"], seed["line_start"], seed["line_end"],
                    seed["evidence"], agent_id=seed.get("agent_id", "seed"),
                )  # fmt: skip
                if seed.get("review", "unreviewed") != "unreviewed":
                    svc.review_finding(finding.finding_id, seed["review"])
        return services[name]

    records_path = run_dir / "runs.jsonl"
    spent = 0.0
    try:
        for n, job in enumerate(jobs, 1):
            if spent >= config.max_total_usd:
                print(f"budget reached (~${spent:.2f}); {len(jobs) - n + 1} jobs not run",
                      file=sys.stderr)  # fmt: skip
                break
            service = service_for(job.state) if job.state else None
            findings_before = service.store.count_findings() if service else None
            tools = LocalTools(project, service, config.service_hops, agent_id=job.arm,
                               compact_reads=job.arm in COMPACT_READ_ARMS)  # fmt: skip
            t0 = time.perf_counter()
            result = run_loop(model, config, job.arm, PROMPT.format(task=job.task.task),
                              tools, spent)  # fmt: skip
            wall_ms = round((time.perf_counter() - t0) * 1000)
            if cost_lookup:  # only for calls whose response carried no charge
                for call in result["calls"]:
                    if call["measured_cost_usd"] is None and call["id"]:
                        call["measured_cost_usd"] = cost_lookup(call["id"])
            usage = summarise_usage(result["calls"], config.model)
            spent += usage["estimated_cost_usd"]["value"] or 0.0
            name = f"{job.task.id}-{job.arm}-{job.role}-{job.rep}"
            with gzip.open(run_dir / "raw" / f"{name}.json.gz", "wt", encoding="utf-8") as fh:
                json.dump(
                    {
                        "messages": result["messages"],
                        "calls": result["calls"],
                        "prune_events": result["prune_events"],
                    },
                    fh,
                    ensure_ascii=False,
                )
            record = {
                "task_id": job.task.id,
                "arm": job.arm,
                "role": job.role,
                "pair": job.pair,
                "repetition": job.rep,
                "error": result["error"],
                "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "wall_ms": {"value": wall_ms, "kind": "measured", "method": "perf_counter"},
                "model_calls": len(result["calls"]),
                "usage": usage,
                "tool_calls": result["tool_calls"],
                "prune_events": result["prune_events"],
                "findings_before": findings_before,
                "findings_after": service.store.count_findings() if service else None,
                "grade": grade(result["answer"], job.rubric),
                "answer": result["answer"],
            }
            with records_path.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            print(
                f"[{n}/{len(jobs)}] {name}: score {record['grade']['score']}, input "
                f"{usage['total_input_tokens']['value']}, ~${usage['estimated_cost_usd']['value']}"
                f"{' ERROR ' + result['error'] if result['error'] else ''}",
                file=sys.stderr,
                flush=True,
            )
    finally:
        for svc in services.values():
            svc.close()
    records = _read_jsonl(records_path)
    meta["finished_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    meta["key_status_after"] = key_status() if key_status else None
    meta["summary"] = summarise(records)
    _write_json(run_dir / "run.json", meta)
    (run_dir / "summary.md").write_text(render_summary(meta, records), encoding="utf-8",
                                        newline="\n")  # fmt: skip
    return run_dir


# -- summaries ---------------------------------------------------------------------------------


def _value(record: dict[str, Any], key: str) -> float | None:
    return record["usage"][key]["value"]


def summarise(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Per arm (follow-up/plain runs only) and paired per-task ratios between arms."""
    rows = [r for r in records if r["role"] != "parent"]
    arms: dict[str, Any] = {}
    for arm in sorted({r["arm"] for r in rows}):
        sel = [r for r in rows if r["arm"] == arm]
        scores = [r["grade"]["score"] for r in sel if r["grade"]["score"] is not None]

        def med(key: str, sel: list[dict[str, Any]] = sel) -> float | None:
            values = [v for r in sel if (v := _value(r, key)) is not None]
            return statistics.median(values) if values else None

        def tot(key: str, sel: list[dict[str, Any]] = sel) -> float | None:
            values = [_value(r, key) for r in sel]
            return None if not values or None in values else round(sum(values), 4)

        arms[arm] = {
            "runs": len(sel),
            "failed_runs": sum(1 for r in sel if r["error"]),
            "mean_score": round(statistics.fmean(scores), 4) if scores else None,
            "median_total_input_tokens": med("total_input_tokens"),
            "median_output_tokens": med("output_tokens"),
            "total_estimated_cost_usd": tot("estimated_cost_usd"),
            "total_measured_cost_usd": tot("measured_cost_usd"),
            "median_tool_calls": statistics.median([len(r["tool_calls"]) for r in sel]),
        }
    parents = [r for r in records if r["role"] == "parent"]
    return {
        "arms": arms,
        "pairs": {f"{a} vs {b}": paired(rows, a, b) for a, b in _comparisons(set(arms))},
        "parent_runs": {
            "runs": len(parents),
            "total_estimated_cost_usd": round(
                sum(_value(r, "estimated_cost_usd") or 0 for r in parents), 4
            ),
            "findings_recorded": [
                r["findings_after"] - (r["findings_before"] or 0)
                for r in parents
                if r["findings_after"] is not None
            ],  # fmt: skip
        },
    }


def _comparisons(arms: set[str]) -> list[tuple[str, str]]:
    wanted = [("LP", "L"), ("LC", "L"), ("LE", "L"), ("SP", "S"), ("S", "L"), ("SM", "SM0"),
              ("TR", "T0"), ("TU", "T0"), ("TR", "TU"), ("X", "L"), ("X", "S"),
              ("SE", "L"), ("SE", "S"), ("TR", "L"), ("TR", "S")]  # fmt: skip
    return [(a, b) for a, b in wanted if a in arms and b in arms]


def paired(rows: list[dict[str, Any]], arm: str, base: str) -> dict[str, Any]:
    """Per-task geometric-mean ratios (arm / base) of tokens and cost, and score difference."""

    def by_task(a: str) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            if r["arm"] == a and not r["error"]:
                out.setdefault(r["task_id"], []).append(r)
        return out

    x, y = by_task(arm), by_task(base)
    tasks = sorted(set(x) & set(y))

    def ratio(key: str) -> float | None:
        logs = []
        for t in tasks:
            a = [v for r in x[t] if (v := _value(r, key))]
            b = [v for r in y[t] if (v := _value(r, key))]
            if a and b:
                logs.append(math.log(statistics.fmean(a) / statistics.fmean(b)))
        return round(math.exp(statistics.fmean(logs)), 4) if logs else None

    diffs = [
        statistics.fmean(r["grade"]["score"] for r in x[t])
        - statistics.fmean(r["grade"]["score"] for r in y[t])
        for t in tasks
    ]
    return {
        "tasks": len(tasks),
        "input_token_ratio": ratio("total_input_tokens"),
        "estimated_cost_ratio": ratio("estimated_cost_usd"),
        "measured_cost_ratio": ratio("measured_cost_usd"),
        "mean_score_difference": round(statistics.fmean(diffs), 4) if diffs else None,
    }


def render_summary(meta: dict[str, Any], records: list[dict[str, Any]]) -> str:
    s = meta["summary"]
    lines = [
        f"# Own-loop experiment: {meta['experiment']} (`{meta['run_id']}`)",
        "",
        f"- Model `{meta['config']['model']}` via OpenRouter (Anthropic provider pinned), "
        f"commit `{(meta['git']['commit'] or 'unknown')[:10]}`"
        + (" (uncommitted changes present)" if meta["git"]["dirty"] else ""),
        "- Tokens are measured (API usage). Estimated cost uses list prices; measured cost is "
        "OpenRouter's reported charge (unavailable if any call's charge was not reported).",
        f"- Only arms of this loop are comparable with each other; {len(records)} records.",
        "",
        "| Arm | Runs | Failed | Mean score | Median input tokens | Median output | "
        "Est. cost | Measured cost | Median tool calls |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for arm, v in s["arms"].items():
        lines.append(
            f"| {arm} | {v['runs']} | {v['failed_runs']} | {v['mean_score']} | "
            f"{v['median_total_input_tokens']} | {v['median_output_tokens']} | "
            f"${v['total_estimated_cost_usd']} | "
            f"{'$' + str(v['total_measured_cost_usd']) if v['total_measured_cost_usd'] is not None else 'unavailable'} | "  # noqa: E501
            f"{v['median_tool_calls']} |"
        )
    if s["pairs"]:
        lines += [
            "",
            "| Comparison | Tasks | Input tokens (ratio) | Est. cost (ratio) | "
            "Measured cost (ratio) | Score difference |",
            "|---|---|---|---|---|---|",
        ]
        for name, p in s["pairs"].items():
            lines.append(
                f"| {name} | {p['tasks']} | {p['input_token_ratio']} | "
                f"{p['estimated_cost_ratio']} | {p['measured_cost_ratio']} | "
                f"{p['mean_score_difference']} |"
            )
    if s["parent_runs"]["runs"]:
        pr = s["parent_runs"]
        lines += [
            "",
            f"Parent (memory-building) runs: {pr['runs']}, "
            f"~${pr['total_estimated_cost_usd']} estimated; "
            f"findings recorded per run: {pr['findings_recorded']}",
        ]
    lines += [
        "",
        "| Task | Arm | Role | Score | Failed checks | Input tokens | Est. cost | "
        "Tool calls | Prunes | Error |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in sorted(records, key=lambda r: (r["task_id"], r["arm"], r["role"], r["repetition"])):
        g = r["grade"]
        lines.append(
            f"| {r['task_id']} | {r['arm']} | {r['role']} | {g['score']} | "
            f"{', '.join(g['failed']) or '-'} | {_value(r, 'total_input_tokens')} | "
            f"{_value(r, 'estimated_cost_usd')} | {len(r['tool_calls'])} | "
            f"{len(r['prune_events'])} | {r['error'] or '-'} |"
        )
    return "\n".join(lines) + "\n"


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
                    newline="\n")  # fmt: skip


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def load_followups(path: Path) -> dict[str, str]:
    """Follow-up task id -> the parent task it builds on (the ``after`` field)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    after = {t["id"]: t.get("after") for t in data["tasks"]}
    missing = [k for k, v in after.items() if not v]
    if missing:
        raise ValueError(f"{path}: follow-up tasks without 'after': {missing}")
    return after


def rubrics_for(path: Path, suite: TaskSuite) -> dict[str, Any]:
    return load_rubrics(path, suite)["rubrics"]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
