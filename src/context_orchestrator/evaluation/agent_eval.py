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

import gzip
import hashlib
import json
import random
import re
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from context_orchestrator.evaluation.claude_cli import parse_claude_cli_result
from context_orchestrator.evaluation.retrieval_eval import EvalTask, TaskSuite, _git_state
from context_orchestrator.memory.loader import discover_files

STRATEGIES = ("A", "B", "B2", "B2C", "B2V", "C", "D", "E")
SERVICE_STRATEGIES = ("B", "B2", "B2C", "B2V")
STRATEGY_NAMES = {
    "A": "full context",
    "B": "context service offered (MCP tool)",
    "B2": "context service, told to use it first",
    "B2C": "as B2, compact packages (excerpts + locations)",
    "B2V": "as B2, told to rely on the verbatim excerpts",
    "C": "no context (file tools only)",
    "D": "oracle (labelled ranges only)",
    "E": "reader sub-agent does all file reading",
}
FILE_TOOLS = ("Read", "Grep", "Glob")
MCP_TOOL = "mcp__ctxo__request_context"
AGENT_TOOL = "Agent"

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
    model: str = "claude-haiku-5-5"  # the published phase 2-3 runs used "haiku" = Haiku 4.5
    strategies: tuple[str, ...] = STRATEGIES
    repetitions: int = 1
    timeout_s: int = 900
    max_budget_usd: float = 3.0  # per run, API-equivalent; a runaway brake, not a target
    service_args: tuple[str, ...] = ("--retrieval", "hybrid", "--hops", "2")
    workers: int = 1  # parallel claude -p sessions
    effort: str | None = None  # claude --effort (low, medium, high, xhigh, max)
    compact_service_args: tuple[str, ...] = ("--detail", "compact", "--per-kind-limit", "8")
    seed: int = 20261011  # run order is shuffled with this seed


SYSTEM_B2 = SYSTEM_B + (
    " Start by calling request_context with the task before you read any files."
)


SYSTEM_B2C = SYSTEM_B2 + (
    " Its results show the opening lines of each relevant place with the file and line"
    " range; read the files you need in full."
)


SYSTEM_B2V = SYSTEM_B2 + (
    " Its excerpts are verbatim with exact file paths and line ranges: rely on them, and"
    " open a file only for parts that were not shown."
)


SYSTEM_E = (
    'You have a sub-agent called reader (Agent tool, subagent_type "reader") that reads the '
    "project's files for you and returns short findings with file paths and line ranges. Do "
    "not read, grep or glob files yourself and do not use other sub-agents: ask the reader "
    "specific questions instead, as often as you need. Always call it in the foreground "
    "(run_in_background: false) and wait for its findings."
)
# The reader's file reading happens in its own context; only its short findings reach the
# main agent. Same model as the main agent so the comparison isolates the context effect.
READER_AGENT = {
    "reader": {
        "description": "Reads the project's files to answer specific questions. Use it for "
        "every lookup in the codebase.",
        "prompt": "You read files in the current project to answer the question you are given. "
        "Use Grep and Glob to locate, Read to confirm. Reply with short findings only: for each "
        "relevant place give the file path, line range and the few key lines quoted verbatim. "
        "No more than 300 words. Say plainly if something does not exist.",
        "tools": ["Read", "Grep", "Glob"],
        "model": "inherit",  # the main agent's model
    }
}


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
    main_tool_calls: list[str] = []
    subagent_result_chars = 0
    subagent_ids: set[str] = set()
    service_result_chars = 0
    service_ids: set[str] = set()
    for event in events:
        content = event.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if block.get("type") == "tool_use":
                tool_calls.append(block.get("name", "?"))
                if not event.get("parent_tool_use_id"):
                    main_tool_calls.append(block.get("name", "?"))
                    if block.get("name") == AGENT_TOOL:
                        subagent_ids.add(block.get("id"))
                if block.get("name") == MCP_TOOL:
                    service_ids.add(block.get("id"))
            elif block.get("type") == "tool_result" and block.get("tool_use_id") in subagent_ids:
                body = block.get("content")
                subagent_result_chars += len(body if isinstance(body, str) else json.dumps(body))
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
        "main_tool_calls": main_tool_calls,
        "subagent_calls": main_tool_calls.count(AGENT_TOOL),
        "subagent_result_chars": subagent_result_chars,
    }


def build_command(
    config: AgentConfig,
    strategy: str,
    prompt: str,
    system_file: Path | None,
    mcp_file: Path | None,
    agents_file: Path | None = None,
) -> list[str]:
    builtin = list(FILE_TOOLS) + ([AGENT_TOOL] if strategy == "E" else [])
    tools = builtin + ([MCP_TOOL] if strategy in SERVICE_STRATEGIES else [])
    cmd = [
        "claude", "-p", prompt,
        "--model", config.model,
        "--output-format", "stream-json", "--verbose",
        "--tools", ",".join(builtin),
        "--allowedTools", " ".join(tools),
        "--disable-slash-commands",
        "--no-session-persistence",
        "--setting-sources", "project",
        "--exclude-dynamic-system-prompt-sections",
        "--strict-mcp-config",
        "--max-budget-usd", str(config.max_budget_usd),
    ]  # fmt: skip
    if config.effort:
        cmd += ["--effort", config.effort]
    if mcp_file is not None:
        cmd += ["--mcp-config", str(mcp_file)]
    if system_file is not None:
        cmd += ["--append-system-prompt-file", str(system_file)]
    if strategy == "E" and agents_file is not None:
        cmd += ["--agents", str(agents_file)]
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
    resume: Path | None = None,
) -> Path:
    """Run every (task, strategy, repetition) and write raw and summarised results.

    Each finished run is appended to ``runs.jsonl`` at once. With ``resume`` (an
    earlier run folder) the stored configuration is reused and only runs that
    are missing or ended in an error are repeated, so a usage limit or a crash
    costs nothing that already finished.
    """
    if resume is not None:
        run_dir = Path(resume)
        meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        stored = dict(meta["config"])
        stored["strategies"] = tuple(stored["strategies"])
        stored["service_args"] = tuple(stored["service_args"])
        config = AgentConfig(**stored)
        task_ids = meta["tasks"]
        run_id = meta["run_id"]
    else:
        config = config or AgentConfig()
        run_id = f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{suite.name}-agent"
        run_dir = Path(out_dir) / run_id
        (run_dir / "raw").mkdir(parents=True)
        meta = {}
    rubric_data = load_rubrics(rubrics_path, suite)
    tasks = [t for t in suite.tasks if not task_ids or t.id in task_ids]
    if not meta:
        meta = {
            "schema_version": 1,
            "run_id": run_id,
            "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "git": _git_state(suite.path.resolve().parent),
            "claude_code_version": _claude_version(runner),
            "config": asdict(config),
            "suite": {"name": suite.name, "sha256": suite.sha256},
            "rubrics_sha256": hashlib.sha256(rubrics_path.read_bytes()).hexdigest(),
            "tasks": [t.id for t in tasks],
            "prompt_template": PROMPT,
            "system_prompts": {
                "B": SYSTEM_B,
                "B2": SYSTEM_B2,
                "B2C": SYSTEM_B2C,
                "B2V": SYSTEM_B2V,
            },  # fmt: skip
            "summary": None,
        }
        _write_meta(run_dir, meta)

    # One read-only copy of the project shared by every run.
    ws = work_dir / run_id
    project = ws / "project"
    if not project.exists():
        shutil.copytree(suite.project, project)
    ctxo = ctxo_command or shutil.which("ctxo") or str(Path(sys.executable).with_name("ctxo"))
    full_file = ws / "full_context.md"
    full_file.write_text(full_context(project), encoding="utf-8")
    meta["full_context_chars"] = len(full_file.read_text(encoding="utf-8"))
    mcp_file = ws / "mcp.json"
    if any(s in SERVICE_STRATEGIES for s in config.strategies):
        _prepare_service(runner, ctxo, project, ws / "state", config.service_args)
    server = {
        "command": ctxo,
        "args": [
            "mcp", str(project), "--state-dir", str(ws / "state"), "--skip-ingest",
            *config.service_args,
        ],
    }  # fmt: skip
    mcp_file.write_text(json.dumps({"mcpServers": {"ctxo": server}}), encoding="utf-8")
    compact_server = {**server, "args": [*server["args"], *config.compact_service_args]}
    mcp_compact = ws / "mcp_compact.json"
    mcp_compact.write_text(json.dumps({"mcpServers": {"ctxo": compact_server}}), "utf-8")
    for name, text in (
        ("system_b.md", SYSTEM_B),
        ("system_b2.md", SYSTEM_B2),
        ("system_b2c.md", SYSTEM_B2C),
        ("system_b2v.md", SYSTEM_B2V),
        ("system_e.md", SYSTEM_E),
    ):
        (ws / name).write_text(text, encoding="utf-8")
    for task in tasks:
        (ws / f"oracle_{task.id}.md").write_text(oracle_context(project, task), encoding="utf-8")
    agents_file = ws / "agents.json"
    agents_file.write_text(json.dumps(READER_AGENT), encoding="utf-8")
    replacements = {str(ws): "<workspace>", str(Path.home()): "<home>"}

    records_path = run_dir / "runs.jsonl"
    done = {
        (r["task_id"], r["strategy"], r["repetition"])
        for r in _read_records(records_path)
        if not r["error"]
    }
    order = [(t, s, r) for r in range(config.repetitions) for t in tasks for s in config.strategies]
    random.Random(config.seed).shuffle(order)
    todo = [(t, s, r) for t, s, r in order if (t.id, s, r) not in done]
    lock = threading.Lock()
    progress = {"done": len(order) - len(todo)}

    def run_one(item: tuple[EvalTask, str, int]) -> None:
        task, strategy, rep = item
        system_file = {
            "A": full_file,
            "B": ws / "system_b.md",
            "B2": ws / "system_b2.md",
            "B2C": ws / "system_b2c.md",
            "B2V": ws / "system_b2v.md",
            "E": ws / "system_e.md",
            "D": ws / f"oracle_{task.id}.md",
        }.get(strategy)
        mcp = {"B": mcp_file, "B2": mcp_file, "B2C": mcp_compact, "B2V": mcp_file}.get(strategy)
        cmd = build_command(
            config, strategy, PROMPT.format(task=task.task), system_file, mcp, agents_file
        )
        t0 = time.perf_counter()
        try:
            proc = runner(
                cmd,
                cwd=project,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=config.timeout_s,
            )
            stdout = proc.stdout.decode("utf-8", "replace")
            stderr = proc.stderr.decode("utf-8", "replace")
            exit_code: int | None = proc.returncode
        except subprocess.TimeoutExpired as exc:
            stdout = (exc.stdout or b"").decode("utf-8", "replace")
            stderr, exit_code = "timeout", None
        wall_ms = round((time.perf_counter() - t0) * 1000)
        name = f"{task.id}-{strategy}-{rep}"
        # Raw event streams are large plain JSON; gzip keeps the repository small (lossless).
        raw_path = run_dir / "raw" / f"{name}.jsonl.gz"
        with gzip.open(raw_path, "wt", encoding="utf-8", newline="\n") as fh:
            fh.write(_sanitise(stdout, replacements))
        parsed = parse_stream(stdout.splitlines())
        usage = parse_claude_cli_result(parsed["result"] or {})
        failed = bool(exit_code != 0 or not parsed["result"] or parsed["result"].get("is_error"))
        error = None
        if failed:
            error = _sanitise((stderr or parsed["plan"])[-500:] or "failed", replacements)
        record = {
            "task_id": task.id,
            "category": task.category,
            "strategy": strategy,
            "repetition": rep,
            "exit_code": exit_code,
            "error": error,
            "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
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
            "main_tool_calls": parsed["main_tool_calls"],
            "subagent_calls": parsed["subagent_calls"],
            "subagent_result_chars": parsed["subagent_result_chars"],
            "grade": grade(parsed["plan"], rubric_data["rubrics"][task.id]),
            "plan": _sanitise(parsed["plan"], replacements),
        }
        with lock:
            with records_path.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            progress["done"] += 1
            print(
                f"[{progress['done']}/{len(order)}] {name}: "
                f"{'ERROR ' if failed else ''}score {record['grade']['score']}, "
                f"input {record['usage']['total_input_tokens']['value']}, "
                f"tools {len(record['tool_calls'])}",
                file=sys.stderr,
                flush=True,
            )

    with ThreadPoolExecutor(max_workers=max(1, config.workers)) as pool:
        list(pool.map(run_one, todo))

    records = _latest_records(_read_records(records_path))
    meta["finished_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    meta["summary"] = summarize_agent_runs(records)
    _write_meta(run_dir, meta)
    (run_dir / "summary.md").write_text(
        render_agent_summary(meta, records), encoding="utf-8", newline="\n"
    )
    return run_dir


def _write_meta(run_dir: Path, meta: dict[str, Any]) -> None:
    (run_dir / "run.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )


def _read_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _latest_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The last attempt per (task, strategy, repetition); earlier failed attempts stay on disk."""
    latest: dict[tuple, dict[str, Any]] = {}
    for r in records:
        latest[(r["task_id"], r["strategy"], r["repetition"])] = r
    return sorted(latest.values(), key=lambda r: (r["task_id"], r["strategy"], r["repetition"]))


def _prepare_service(
    runner: Callable[..., Any], ctxo: str, project: Path, state: Path, service_args: tuple[str, ...]
) -> None:
    """Build the service's index (and embeddings) once, before parallel runs share it."""
    keep = {"--retrieval", "--embed-model", "--ollama-url"}
    args = list(service_args)
    ingest_args = [x for i, x in enumerate(args) if x in keep or (i and args[i - 1] in keep)]
    cmd = [ctxo, "ingest", str(project), "--state-dir", str(state), *ingest_args]
    proc = runner(cmd, capture_output=True, timeout=1800)
    if proc.returncode != 0:
        raise RuntimeError(
            "preparing the context service failed (is Ollama running for hybrid retrieval?): "
            + proc.stderr.decode("utf-8", "replace")[-500:]
        )


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
