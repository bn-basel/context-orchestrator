"""Phase 2: compare context strategies with a real agent (Claude Code, ``claude -p``).

Every run gives the same model the same task, prompt template and read-only
file tools (Read, Grep, Glob) in a copy of the project. Only the context
strategy differs:

* ``A`` full context: the whole project text appended to the system prompt.
* ``B`` context service: the ``request_context`` MCP tool is added.
* ``C`` no context: the agent explores the files with its tools.
* ``D`` oracle: only the hand-labelled relevant line ranges are appended.

The agent writes a short implementation plan, graded against a per-task
rubric of regex checks (``benchmarks/tasks/<suite>.rubrics.json``). Usage
comes from Claude Code's own result event and is labelled measured, or
estimated for its API-list-price ``costUSD``. On a subscription that cost is
not what the owner pays; it is an API-equivalent figure.

Raw streams are stored (with local paths and session ids replaced) so every
number can be recomputed from the files.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from context_orchestrator.evaluation.claude_cli import parse_claude_cli_result
from context_orchestrator.evaluation.retrieval_eval import EvalTask, TaskSuite, _git_state
from context_orchestrator.memory.loader import discover_files

STRATEGIES = ("A", "B", "C", "D")
STRATEGY_NAMES = {
    "A": "full context",
    "B": "context service (MCP tool)",
    "C": "no context (file tools only)",
    "D": "oracle (labelled ranges only)",
}
FILE_TOOLS = ("Read", "Grep", "Glob")
MCP_TOOL = "mcp__ctxo__request_context"

PROMPT = """You are an engineer on the Hallpass project, whose code and docs are in the current \
directory.

Task: {task}

Write a short implementation plan (at most 300 words): which files and functions to change, \
which project decisions, constraints and known issues apply, and the main risks. Name file \
paths. Do not modify any files. If something the task asks about does not exist in the \
project, say so plainly."""

SYSTEM_B = (
    "A context service is available as the tool request_context. It returns relevant project "
    "knowledge (decisions, schema, conventions, known issues, code, tests) with file paths and "
    "trust labels. Use it to find what you need; you may call it several times with follow-up "
    "questions, and read files directly when you need more."
)


@dataclass(frozen=True, slots=True)
class AgentConfig:
    model: str = "haiku"
    strategies: tuple[str, ...] = STRATEGIES
    repetitions: int = 1
    timeout_s: int = 900
    max_budget_usd: float = 3.0  # per run, API-equivalent; a runaway brake, not a target
    service_args: tuple[str, ...] = ("--retrieval", "hybrid", "--hops", "2")


# -- context for each strategy -----------------------------------------------------------


def full_context(project: Path) -> str:
    parts = ["# Full project knowledge base (every file)\n"]
    for path in discover_files(project):
        rel = path.relative_to(project).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if text.strip():
            parts.append(f"\n=== {rel} ===\n{text.rstrip()}\n")
    return "".join(parts)


def oracle_context(project: Path, task: EvalTask) -> str:
    parts = ["# Project knowledge selected for this task\n"]
    for label in task.relevant:
        lines = (project / label.path).read_text(encoding="utf-8").splitlines()
        excerpt = "\n".join(lines[label.line_start - 1 : label.line_end])
        parts.append(f"\n=== {label.label()} ===\n{excerpt}\n")
    return "".join(parts)


# -- grading -------------------------------------------------------------------------------


def grade(plan: str, rubric: dict[str, Any]) -> dict[str, Any]:
    def hit(check: dict[str, Any]) -> bool:
        return any(re.search(p, plan, re.IGNORECASE) for p in check["any_of"])

    checks = rubric.get("checks", [])
    passed = [c["id"] for c in checks if hit(c)]
    violated = [c["id"] for c in rubric.get("must_not", []) if hit(c)]
    return {
        "score": round(len(passed) / len(checks), 4) if checks else None,
        "passed": passed,
        "failed": [c["id"] for c in checks if c["id"] not in passed],
        "must_not_violated": violated,
        "success": bool(checks) and len(passed) == len(checks) and not violated,
    }


def load_rubrics(path: Path, suite: TaskSuite) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rubrics = data["rubrics"]
    problems = []
    for task in suite.tasks:
        rubric = rubrics.get(task.id)
        if rubric is None:
            problems.append(f"{task.id}: no rubric")
            continue
        bad_regex = False
        for check in rubric.get("checks", []) + rubric.get("must_not", []):
            for pattern in check["any_of"]:
                try:
                    re.compile(pattern)
                except re.error as exc:
                    bad_regex = True
                    problems.append(f"{task.id}/{check['id']}: bad regex {pattern!r} ({exc})")
        if bad_regex:
            continue
        if "example_pass" in rubric and not grade(rubric["example_pass"], rubric)["success"]:
            problems.append(f"{task.id}: example_pass does not pass its own rubric")
    if problems:
        raise ValueError(f"{path}: invalid rubrics:\n  " + "\n  ".join(problems))
    return data


# -- running -------------------------------------------------------------------------------


def _sanitise(text: str, replacements: dict[str, str]) -> str:
    """Replace local paths, the OS user name and session ids in stored output.

    Paths appear plain, JSON-escaped and inside Claude Code's own folder names
    (``C--Users-<name>-AppData-...``), so the user name is replaced on its own too.
    """
    for old, new in replacements.items():
        text = text.replace(old, new).replace(old.replace("\\", "\\\\"), new)
    user = Path.home().name
    if len(user) >= 3:
        text = re.sub(re.escape(user), "<user>", text, flags=re.IGNORECASE)
    return re.sub(r'"session_id":\s*"[^"]+"', '"session_id": "<session>"', text)


def parse_stream(lines: list[str]) -> dict[str, Any]:
    events = [json.loads(line) for line in lines if line.strip().startswith("{")]
    tool_calls: list[str] = []
    service_result_chars = 0
    service_ids: set[str] = set()
    for event in events:
        content = event.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if block.get("type") == "tool_use":
                tool_calls.append(block.get("name", "?"))
                if block.get("name") == MCP_TOOL:
                    service_ids.add(block.get("id"))
            elif block.get("type") == "tool_result" and block.get("tool_use_id") in service_ids:
                body = block.get("content")
                text = body if isinstance(body, str) else json.dumps(body)
                service_result_chars += len(text)
    result = next((e for e in reversed(events) if e.get("type") == "result"), None)
    return {
        "result": result,
        "plan": (result or {}).get("result") or "",
        "tool_calls": tool_calls,
        "service_calls": tool_calls.count(MCP_TOOL),
        "service_result_chars": service_result_chars,
    }


def build_command(
    config: AgentConfig, strategy: str, prompt: str, system_file: Path | None, mcp_file: Path | None
) -> list[str]:
    tools = list(FILE_TOOLS) + ([MCP_TOOL] if strategy == "B" else [])
    cmd = [
        "claude", "-p", prompt,
        "--model", config.model,
        "--output-format", "stream-json", "--verbose",
        "--tools", ",".join(FILE_TOOLS),
        "--allowedTools", " ".join(tools),
        "--disable-slash-commands",
        "--no-session-persistence",
        "--setting-sources", "project",
        "--exclude-dynamic-system-prompt-sections",
        "--strict-mcp-config",
        "--max-budget-usd", str(config.max_budget_usd),
    ]  # fmt: skip
    if mcp_file is not None:
        cmd += ["--mcp-config", str(mcp_file)]
    if system_file is not None:
        cmd += ["--append-system-prompt-file", str(system_file)]
    return cmd


def run_agent_suite(
    suite: TaskSuite,
    rubrics_path: Path,
    out_dir: Path | str,
    work_dir: Path,
    config: AgentConfig | None = None,
    task_ids: list[str] | None = None,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    ctxo_command: str | None = None,
) -> Path:
    """Run every (task, strategy, repetition) and write raw and summarised results."""
    config = config or AgentConfig()
    rubric_data = load_rubrics(rubrics_path, suite)
    tasks = [t for t in suite.tasks if not task_ids or t.id in task_ids]
    git_state = _git_state(suite.path.resolve().parent)
    started_at = datetime.now(UTC)
    run_id = f"{started_at:%Y%m%dT%H%M%SZ}-{suite.name}-agent"
    run_dir = Path(out_dir) / run_id
    (run_dir / "raw").mkdir(parents=True)

    # One read-only copy of the project for every run; service state is shared and warmed.
    ws = work_dir / run_id
    project = ws / "project"
    shutil.copytree(suite.project, project)
    ctxo = ctxo_command or shutil.which("ctxo") or str(Path(sys.executable).with_name("ctxo"))
    mcp_file = ws / "mcp.json"
    mcp_file.write_text(json.dumps({"mcpServers": {"ctxo": {
        "command": ctxo,
        "args": ["mcp", str(project), "--state-dir", str(ws / "state"), *config.service_args],
    }}}), encoding="utf-8")  # fmt: skip
    full_file = ws / "full_context.md"
    full_file.write_text(full_context(project), encoding="utf-8")
    replacements = {str(ws): "<workspace>", str(Path.home()): "<home>"}

    records = []
    order = [(t, s, r) for r in range(config.repetitions) for t in tasks for s in config.strategies]
    for task, strategy, rep in order:
        system_file = None
        if strategy == "A":
            system_file = full_file
        elif strategy == "B":
            system_file = ws / "system_b.md"
            system_file.write_text(SYSTEM_B, encoding="utf-8")
        elif strategy == "D":
            system_file = ws / f"oracle_{task.id}.md"
            system_file.write_text(oracle_context(project, task), encoding="utf-8")
        prompt = PROMPT.format(task=task.task)
        cmd = build_command(
            config, strategy, prompt, system_file, mcp_file if strategy == "B" else None
        )
        t0 = time.perf_counter()
        try:
            proc = runner(cmd, cwd=project, stdin=subprocess.DEVNULL, capture_output=True,
                          timeout=config.timeout_s)  # fmt: skip
            stdout = proc.stdout.decode("utf-8", "replace")
            stderr = proc.stderr.decode("utf-8", "replace")
            exit_code: int | None = proc.returncode
        except subprocess.TimeoutExpired as exc:
            stdout = (exc.stdout or b"").decode("utf-8", "replace")
            stderr, exit_code = "timeout", None
        wall_ms = round((time.perf_counter() - t0) * 1000)

        name = f"{task.id}-{strategy}-{rep}"
        (run_dir / "raw" / f"{name}.jsonl").write_text(
            _sanitise(stdout, replacements), encoding="utf-8", newline="\n"
        )
        parsed = parse_stream(stdout.splitlines())
        usage = parse_claude_cli_result(parsed["result"] or {})
        record = {
            "task_id": task.id,
            "category": task.category,
            "strategy": strategy,
            "repetition": rep,
            "exit_code": exit_code,
            "error": None
            if exit_code == 0 and parsed["result"]
            else _sanitise(stderr[-500:], replacements),
            "wall_ms": {
                "value": wall_ms,
                "kind": "measured",
                "method": "perf_counter around claude -p",
            },
            "usage": {k: asdict(v) for k, v in _usage_fields(usage).items()},
            "num_turns": usage.num_turns,
            "tool_calls": parsed["tool_calls"],
            "service_calls": parsed["service_calls"],
            "service_result_chars": parsed["service_result_chars"],
            "grade": grade(parsed["plan"], rubric_data["rubrics"][task.id]),
            "plan": _sanitise(parsed["plan"], replacements),
        }
        records.append(record)
        print(f"{name}: score {record['grade']['score']}, "
              f"input {record['usage']['total_input_tokens']['value']}, "
              f"tools {len(record['tool_calls'])}", file=sys.stderr, flush=True)  # fmt: skip

    with (run_dir / "runs.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    meta = {
        "schema_version": 1,
        "run_id": run_id,
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "git": git_state,
        "claude_code_version": _claude_version(runner),
        "config": asdict(config),
        "suite": {"name": suite.name, "sha256": suite.sha256},
        "rubrics_sha256": hashlib.sha256(rubrics_path.read_bytes()).hexdigest(),
        "tasks": [t.id for t in tasks],
        "prompt_template": PROMPT,
        "system_b": SYSTEM_B,
        "full_context_chars": len(full_file.read_text(encoding="utf-8")),
        "summary": summarize_agent_runs(records),
    }
    (run_dir / "run.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    (run_dir / "summary.md").write_text(
        render_agent_summary(meta, records), encoding="utf-8", newline="\n"
    )
    return run_dir


def _usage_fields(usage: Any) -> dict[str, Any]:
    return {
        "input_tokens": usage.input_tokens,
        "cache_read_input_tokens": usage.cache_read_input_tokens,
        "cache_creation_input_tokens": usage.cache_creation_input_tokens,
        "total_input_tokens": usage.total_input_tokens,
        "output_tokens": usage.output_tokens,
        "duration_ms": usage.duration_ms,
        "api_equivalent_cost_usd": usage.api_equivalent_cost_usd,
    }


def _claude_version(runner: Callable[..., Any]) -> str | None:
    try:
        proc = runner(["claude", "--version"], capture_output=True, timeout=30)
        return proc.stdout.decode("utf-8", "replace").strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


# -- summarising -----------------------------------------------------------------------------


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def summarize_agent_runs(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Per strategy: quality and measured usage. Unavailable values are excluded and counted."""
    out: dict[str, Any] = {}
    for strategy in sorted({r["strategy"] for r in records}):
        rows = [r for r in records if r["strategy"] == strategy]

        def values(key: str, rows: list[dict[str, Any]] = rows) -> list[float]:
            return [r["usage"][key]["value"] for r in rows if r["usage"][key]["value"] is not None]

        scores = [r["grade"]["score"] for r in rows if r["grade"]["score"] is not None]
        out[strategy] = {
            "name": STRATEGY_NAMES.get(strategy, strategy),
            "runs": len(rows),
            "failed_runs": sum(1 for r in rows if r["error"]),
            "mean_score": round(sum(scores) / len(scores), 4) if scores else None,
            "successes": sum(1 for r in rows if r["grade"]["success"]),
            "must_not_violations": sum(len(r["grade"]["must_not_violated"]) for r in rows),
            "median_total_input_tokens": _median(values("total_input_tokens")),
            "median_uncached_input_tokens": _median(values("input_tokens")),
            "median_cache_read_tokens": _median(values("cache_read_input_tokens")),
            "median_cache_write_tokens": _median(values("cache_creation_input_tokens")),
            "median_output_tokens": _median(values("output_tokens")),
            "median_duration_ms": _median(values("duration_ms")),
            "total_api_equivalent_cost_usd": round(sum(values("api_equivalent_cost_usd")), 4),
            "usage_unavailable_runs": sum(
                1 for r in rows if r["usage"]["total_input_tokens"]["value"] is None
            ),
            "median_tool_calls": _median([len(r["tool_calls"]) for r in rows]),
            "median_service_calls": _median([r["service_calls"] for r in rows]),
        }
    return out


def render_agent_summary(meta: dict[str, Any], records: list[dict[str, Any]]) -> str:
    s = meta["summary"]
    lines = [
        f"# Agent comparison: {meta['suite']['name']} (`{meta['run_id']}`)",
        "",
        f"- Model `{meta['config']['model']}`, {meta['claude_code_version']}, "
        f"commit `{(meta['git']['commit'] or 'unknown')[:10]}`"
        + (" (uncommitted changes present)" if meta["git"]["dirty"] else ""),
        f"- Tasks: {', '.join(meta['tasks'])}; repetitions: {meta['config']['repetitions']}",
        f"- Service config for B: `{' '.join(meta['config']['service_args'])}`",
        "- Tokens and durations are measured (reported by Claude Code); cost is the CLI's "
        "API-list-price estimate, **not** a subscription charge.",
        "",
        "| Strategy | Runs | Mean score | Successes | Traps hit | Median input tokens "
        "(uncached / cache read / cache write) | Median output | Median duration | "
        "API-equiv. cost (total) | Median tool calls (service) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for key, v in s.items():
        lines.append(
            f"| {key}: {v['name']} | {v['runs']} | {v['mean_score']} | {v['successes']} | "
            f"{v['must_not_violations']} | {v['median_total_input_tokens']} "
            f"({v['median_uncached_input_tokens']} / {v['median_cache_read_tokens']} / "
            f"{v['median_cache_write_tokens']}) | {v['median_output_tokens']} | "
            f"{v['median_duration_ms']} ms | ${v['total_api_equivalent_cost_usd']} | "
            f"{v['median_tool_calls']} ({v['median_service_calls']}) |"
        )
    lines += ["", "| Task | Strategy | Score | Failed checks | Traps | Input tokens | Tools |",
              "|---|---|---|---|---|---|---|"]  # fmt: skip
    for r in records:
        g = r["grade"]
        lines.append(
            f"| {r['task_id']} | {r['strategy']} | {g['score']} | {', '.join(g['failed']) or '-'} "
            f"| {', '.join(g['must_not_violated']) or '-'} "
            f"| {r['usage']['total_input_tokens']['value']} | {len(r['tool_calls'])} |"
        )
    return "\n".join(lines) + "\n"
