"""Command-line interface: ``ctxo ingest`` and ``ctxo request``.

JSON output is the machine interface for agents that can run shell commands;
Markdown output is what a human (or a prompt) would read.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import sys
from pathlib import Path

from context_orchestrator.agent_interface.api import ContextService
from context_orchestrator.models import (
    DEFAULT_MAX_REFERENCES,
    DEFAULT_MIN_RELATIVE_SCORE,
    ContextRequest,
    InfoKind,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ctxo", description="Context orchestrator for AI agents.")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging to stderr")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("project", type=Path, help="project root directory")
        p.add_argument(
            "--state-dir",
            type=Path,
            help="where memory.db and telemetry live (default: <project>/.ctxo)",
        )

    ingest = sub.add_parser("ingest", help="load or refresh the project knowledge base")
    common(ingest)

    req = sub.add_parser("request", help="request a context package")
    common(req)
    req.add_argument("--task", help="what the agent is trying to do")
    req.add_argument(
        "--kind",
        action="append",
        default=[],
        choices=[k.value for k in InfoKind],
        help="kind of information wanted (repeatable; default: any)",
    )
    req.add_argument("--constraint", action="append", default=[], help="constraint (repeatable)")
    req.add_argument("--max-tokens", type=int, default=4000)
    req.add_argument("--per-kind-limit", type=int, default=3)
    req.add_argument("--min-relative-score", type=float, default=DEFAULT_MIN_RELATIVE_SCORE)
    req.add_argument("--max-references", type=int, default=DEFAULT_MAX_REFERENCES)
    req.add_argument("--agent-id", default="cli")
    req.add_argument("--request-file", type=Path, help="read the request from a JSON file")
    req.add_argument("--format", choices=["json", "markdown"], default="json")
    req.add_argument(
        "--record-task-text",
        action="store_true",
        help="store task text and query terms in telemetry (off by default)",
    )

    ev = sub.add_parser("eval-retrieval", help="score retrieval against a labelled task suite")
    ev.add_argument("suite", type=Path, help="task suite JSON (see benchmarks/tasks/)")
    ev.add_argument("--gate", type=Path, help="gate criteria JSON (e.g. benchmarks/gate1.json)")
    ev.add_argument(
        "--out",
        type=Path,
        default=Path("benchmarks/results"),
        help="directory for raw run results (default: benchmarks/results)",
    )
    ev.add_argument("--max-tokens", type=int, default=4000)
    ev.add_argument("--per-kind-limit", type=int, default=3)
    ev.add_argument("--min-relative-score", type=float, default=DEFAULT_MIN_RELATIVE_SCORE)
    ev.add_argument("--max-references", type=int, default=DEFAULT_MAX_REFERENCES)
    return parser


def _eval_retrieval(args: argparse.Namespace) -> int:
    from context_orchestrator.evaluation.retrieval_eval import (
        RetrievalConfig,
        load_suite,
        run_suite,
    )

    suite = load_suite(args.suite)
    gate = json.loads(args.gate.read_text(encoding="utf-8")) if args.gate else None
    run = run_suite(
        suite,
        args.out,
        RetrievalConfig(
            args.max_tokens, args.per_kind_limit, args.min_relative_score, args.max_references
        ),
        gate=gate,
        gate_path=args.gate,
    )
    print((run.run_dir / "summary.md").read_text(encoding="utf-8"))
    print(f"Raw results: {run.run_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    with contextlib.suppress(AttributeError, ValueError):  # Windows consoles use a legacy code page
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    if args.command == "eval-retrieval":
        try:
            return _eval_retrieval(args)
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    if not args.project.is_dir():
        print(f"error: project directory not found: {args.project}", file=sys.stderr)
        return 2

    try:
        if args.command == "ingest":
            with ContextService(args.project, args.state_dir) as svc:
                report = svc.ingest()
                print(
                    json.dumps(
                        {
                            "state_dir": str(svc.state_dir),
                            "added": report.added,
                            "updated": report.updated,
                            "unchanged": len(report.unchanged),
                            "removed": report.removed,
                            "skipped": report.skipped,
                            "chunks_written": report.chunks_written,
                            "total_chunks": svc.store.count_chunks(),
                        },
                        indent=2,
                    )
                )
            return 0

        if args.request_file:
            data = json.loads(args.request_file.read_text(encoding="utf-8"))
        elif args.task:
            data = {
                "task": args.task,
                "kinds": args.kind,
                "constraints": args.constraint,
                "max_tokens": args.max_tokens,
                "per_kind_limit": args.per_kind_limit,
                "min_relative_score": args.min_relative_score,
                "max_references": args.max_references,
                "agent_id": args.agent_id,
            }
        else:
            print("error: give --task or --request-file", file=sys.stderr)
            return 2
        request = ContextRequest.from_dict(data)
        with ContextService(
            args.project, args.state_dir, record_task_text=args.record_task_text
        ) as svc:
            package = svc.request(request)
        if args.format == "markdown":
            print(package.render_markdown())
        else:
            print(json.dumps(package.to_dict(), indent=2, ensure_ascii=False))
        return 0
    except (ValueError, RuntimeError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
