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
import tempfile
from pathlib import Path

from context_orchestrator.agent_interface.api import RETRIEVAL_MODES, ContextService
from context_orchestrator.models import (
    DEFAULT_DETAIL,
    DEFAULT_HOPS,
    DEFAULT_MAX_REFERENCES,
    DEFAULT_MIN_RELATIVE_SCORE,
    DETAIL_LEVELS,
    ContextRequest,
    InfoKind,
)
from context_orchestrator.retrieval.semantic import (
    DEFAULT_MODEL,
    DEFAULT_OLLAMA_URL,
    OllamaEmbedder,
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
        retrieval_options(p)

    def retrieval_options(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--retrieval",
            choices=RETRIEVAL_MODES,
            default="bm25",
            help="bm25 (default), hybrid or semantic; the last two need Ollama",
        )
        p.add_argument("--embed-model", default=DEFAULT_MODEL)
        p.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)

    mcp = sub.add_parser("mcp", help="serve the context service as an MCP tool over stdio")
    common(mcp)
    mcp.add_argument("--max-tokens", type=int, default=4000)
    mcp.add_argument("--per-kind-limit", type=int, default=3)
    mcp.add_argument("--hops", type=int, choices=[1, 2], default=DEFAULT_HOPS)
    mcp.add_argument("--detail", choices=DETAIL_LEVELS, default=DEFAULT_DETAIL)
    mcp.add_argument(
        "--skip-ingest",
        action="store_true",
        help="serve the existing knowledge base without refreshing it",
    )
    mcp.add_argument(
        "--memory-write",
        action="store_true",
        help="also offer record_finding, so agents can save anchored findings (state dir only)",
    )

    fnd = sub.add_parser("findings", help="list findings agents have recorded, and review them")
    common(fnd)
    fnd.add_argument(
        "--confirm",
        action="append",
        default=[],
        metavar="ID",
        help="mark a finding as checked and correct (served as verified)",
    )
    fnd.add_argument("--reject", action="append", default=[], metavar="ID",
                     help="mark a finding as wrong (no longer served)")  # fmt: skip

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
    req.add_argument("--hops", type=int, choices=[1, 2], default=DEFAULT_HOPS)
    req.add_argument("--detail", choices=DETAIL_LEVELS, default=DEFAULT_DETAIL)
    req.add_argument("--agent-id", default="cli")
    req.add_argument("--request-file", type=Path, help="read the request from a JSON file")
    req.add_argument("--format", choices=["json", "markdown"], default="json")
    req.add_argument(
        "--record-task-text",
        action="store_true",
        help="store task text and query terms in telemetry (off by default)",
    )

    wi = sub.add_parser("what-if", help="replay recorded runs under alternative policies")
    wi.add_argument("run_dir", type=Path)
    wi.add_argument("--suite", type=Path, required=True)

    tr = sub.add_parser("analyze-traces", help="what agents read in an eval-agent run")
    tr.add_argument("run_dir", type=Path)
    tr.add_argument("--suite", type=Path, required=True)

    an = sub.add_parser("analyze-agent", help="paired analysis of an eval-agent run folder")
    an.add_argument("run_dir", type=Path)

    ag = sub.add_parser("eval-agent", help="phase 2: compare context strategies with claude -p")
    ag.add_argument("suite", type=Path)
    ag.add_argument("--rubrics", type=Path, required=True)
    ag.add_argument("--tasks", help="comma-separated task ids (default: all)")
    ag.add_argument("--strategies", default="A,B,C,D")
    ag.add_argument("--model", default="claude-haiku-5-5")
    ag.add_argument("--reps", type=int, default=1)
    ag.add_argument("--max-budget-usd", type=float, default=3.0)
    ag.add_argument("--workers", type=int, default=1, help="parallel claude sessions")
    ag.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"])
    ag.add_argument("--seed", type=int, default=20261011, help="run-order shuffle seed")
    ag.add_argument(
        "--resume", type=Path, help="continue an earlier run folder (reuses its stored settings)"
    )
    ag.add_argument(
        "--service-args",
        default="--retrieval hybrid --hops 2",
        help="extra arguments for `ctxo mcp` in strategy B",
    )
    ag.add_argument("--out", type=Path, default=Path("benchmarks/results"))
    ag.add_argument(
        "--work-dir", type=Path, default=Path(tempfile.gettempdir()) / "ctxo-agent-runs"
    )

    lp = sub.add_parser(
        "loop-probe", help="one tiny call through the own agent loop's API route (costs ~$0.0001)"
    )
    lp.add_argument("--model", default="anthropic/claude-haiku-5.5")

    le = sub.add_parser("loop-eval", help="phase 4-5 experiments in the own agent loop")
    le.add_argument("experiment", choices=["prune", "memory", "trust", "combo"],
                    help="prune: plain arms side by side (L, LP, LC, LE, S, SP); memory: "
                    "parent then follow-up; trust: follow-ups on seeded findings; combo: L, S "
                    "and X (all working levers) on the follow-ups")  # fmt: skip
    le.add_argument("suite", type=Path, help="task suite (memory: the follow-up suite)")
    le.add_argument("--rubrics", type=Path, required=True)
    le.add_argument("--parents", type=Path, help="memory: suite holding the parent tasks")
    le.add_argument("--parent-rubrics", type=Path, help="memory: rubrics for the parents")
    le.add_argument("--arms", default="L,LP", help="prune experiment arms (L, LP, LC, LE, S, SP)")
    le.add_argument("--findings", type=Path, help="trust: reviewed findings to seed")
    le.add_argument("--tasks", help="comma-separated task ids (default: all)")
    le.add_argument("--reps", type=int, default=1)
    le.add_argument("--model", default="anthropic/claude-haiku-5.5")
    le.add_argument("--max-total-usd", type=float, default=2.0, help="estimated; hard stop")
    le.add_argument("--dry-run", action="store_true", help="list the runs; call nothing")
    le.add_argument("--seed", type=int, default=20261011)
    le.add_argument("--out", type=Path, default=Path("benchmarks/results"))
    le.add_argument("--work-dir", type=Path, default=Path(tempfile.gettempdir()) / "ctxo-loop-runs")

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
    ev.add_argument("--hops", type=int, choices=[1, 2], default=DEFAULT_HOPS)
    ev.add_argument("--detail", choices=DETAIL_LEVELS, default=DEFAULT_DETAIL)
    retrieval_options(ev)
    return parser


def _embedder(args: argparse.Namespace) -> OllamaEmbedder | None:
    if args.retrieval == "bm25":
        return None
    return OllamaEmbedder(model=args.embed_model, base_url=args.ollama_url)


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
            args.max_tokens,
            args.per_kind_limit,
            args.min_relative_score,
            args.max_references,
            args.hops,
            args.detail,
            args.retrieval,
            args.embed_model if args.retrieval != "bm25" else None,
        ),
        embedder=_embedder(args),
        gate=gate,
        gate_path=args.gate,
    )
    print((run.run_dir / "summary.md").read_text(encoding="utf-8"))
    print(f"Raw results: {run.run_dir}")
    return 0


def _loop_probe(args: argparse.Namespace) -> int:
    from context_orchestrator.evaluation import own_loop

    status = own_loop.openrouter_key_status()
    print(f"key status (USD): {status}")
    if status is not None and status.get("limit") is None:
        print("warning: this key has no credit limit; set one on openrouter.ai before experiments")
    model = own_loop.openrouter_model()
    turn = model(
        model=args.model,
        max_tokens=1024,  # thinking counts toward it
        output_config={"effort": own_loop.EFFORT},
        messages=[{"role": "user", "content": "Reply with the single word OK."}],
    )
    print(f"response id: {turn.id}\nstop_reason: {turn.stop_reason}")
    print(f"content: {turn.content}\nusage: {json.dumps(turn.usage)}")
    print(f"estimated cost: {own_loop.estimate_cost(args.model, turn.usage)}")
    print(f"measured cost (OpenRouter's charge in the usage): {turn.usage.get('cost')}")
    return 0


def _loop_eval(args: argparse.Namespace) -> int:
    from context_orchestrator.evaluation import own_loop
    from context_orchestrator.evaluation.retrieval_eval import load_suite

    suite = load_suite(args.suite)
    rubrics = own_loop.rubrics_for(args.rubrics, suite)
    task_ids = args.tasks.split(",") if args.tasks else None
    config = own_loop.LoopConfig(
        model=args.model,
        max_total_usd=args.max_total_usd,
        seed=args.seed,
    )
    meta: dict = {
        "suite": {"name": suite.name, "sha256": suite.sha256},
        "rubrics_sha256": own_loop.sha256_file(args.rubrics),
    }
    if args.experiment == "prune":
        arms = [a.strip() for a in args.arms.split(",")]
        plain = ("L", "LP", "LC", "LE", "S", "SP")
        unknown = [a for a in arms if a not in plain]
        if unknown:
            raise ValueError(f"prune arms are {', '.join(plain)}; not {unknown}")
        jobs = own_loop.plan_prune(suite, rubrics, arms, args.reps, task_ids, args.seed)
    elif args.experiment in ("trust", "combo"):
        if not args.findings:
            raise ValueError(f"the {args.experiment} experiment needs --findings")
        seeds = own_loop.trust_seeds(args.findings)
        plan = own_loop.plan_trust if args.experiment == "trust" else own_loop.plan_combo
        jobs = plan(suite, rubrics, args.reps, task_ids, args.seed)
        meta["findings"] = {"file": args.findings.as_posix(),
                            "sha256": own_loop.sha256_file(args.findings),
                            "seeded": len(seeds["trusted"])}  # fmt: skip
    else:
        if not (args.parents and args.parent_rubrics):
            raise ValueError("the memory experiment needs --parents and --parent-rubrics")
        parents = load_suite(args.parents)
        jobs = own_loop.plan_memory(
            suite, rubrics, parents, own_loop.rubrics_for(args.parent_rubrics, parents),
            own_loop.load_followups(args.suite), args.reps, task_ids, args.seed,
        )  # fmt: skip
        meta["parents"] = {"name": parents.name, "sha256": parents.sha256}
        meta["parent_rubrics_sha256"] = own_loop.sha256_file(args.parent_rubrics)
    print(f"{len(jobs)} runs planned (hard stop at ~${args.max_total_usd} estimated):")
    for job in jobs:
        print(f"  {job.task.id} {job.arm} {job.role} rep {job.rep}")
    if args.dry_run:
        return 0
    run_dir = own_loop.run_experiment(
        args.experiment, jobs, suite.project, args.out, args.work_dir, config, meta,
        seeds=seeds if args.experiment in ("trust", "combo") else None,
    )  # fmt: skip
    print((run_dir / "summary.md").read_text(encoding="utf-8"))
    print(f"Raw results: {run_dir}")
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
    if args.command == "what-if":
        from context_orchestrator.evaluation.retrieval_eval import load_suite
        from context_orchestrator.evaluation.what_if import write_what_if

        try:
            out = write_what_if(args.run_dir, load_suite(args.suite))
        except (OSError, ValueError, KeyError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(out.read_text(encoding="utf-8"))
        return 0
    if args.command == "analyze-traces":
        from context_orchestrator.evaluation.retrieval_eval import load_suite
        from context_orchestrator.evaluation.trace_analysis import write_trace_analysis

        try:
            out = write_trace_analysis(args.run_dir, load_suite(args.suite))
        except (OSError, ValueError, KeyError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(out.read_text(encoding="utf-8"))
        return 0
    if args.command == "analyze-agent":
        from context_orchestrator.evaluation.agent_analysis import write_analysis

        try:
            out = write_analysis(args.run_dir)
        except (OSError, ValueError, KeyError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(out.read_text(encoding="utf-8"))
        return 0
    if args.command == "eval-agent":
        from context_orchestrator.evaluation.agent_eval import AgentConfig, run_agent_suite
        from context_orchestrator.evaluation.retrieval_eval import load_suite

        try:
            config = AgentConfig(
                model=args.model,
                strategies=tuple(s.strip() for s in args.strategies.split(",")),
                repetitions=args.reps,
                max_budget_usd=args.max_budget_usd,
                service_args=tuple(args.service_args.split()),
                workers=args.workers,
                effort=args.effort,
                seed=args.seed,
            )
            run_dir = run_agent_suite(
                load_suite(args.suite), args.rubrics, args.out, args.work_dir, config,
                task_ids=args.tasks.split(",") if args.tasks else None,
                resume=args.resume,
            )  # fmt: skip
        except (ValueError, OSError, RuntimeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print((run_dir / "summary.md").read_text(encoding="utf-8"))
        print(f"Raw results: {run_dir}")
        return 0
    if args.command == "loop-probe":
        try:
            return _loop_probe(args)
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    if args.command == "loop-eval":
        try:
            return _loop_eval(args)
        except (ValueError, OSError, RuntimeError, KeyError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
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
        if args.command == "mcp":
            from context_orchestrator.agent_interface.mcp_server import (
                McpServer,
                ServerConfig,
                run_stdio,
            )

            with ContextService(
                args.project, args.state_dir, retrieval=args.retrieval, embedder=_embedder(args)
            ) as svc:
                if not args.skip_ingest:
                    svc.ingest()
                logging.getLogger(__name__).info("mcp: %d chunks ready", svc.store.count_chunks())
                config = ServerConfig(
                    args.max_tokens, args.per_kind_limit, args.hops, args.detail, args.memory_write
                )
                run_stdio(McpServer(svc, config))
            return 0

        if args.command == "findings":
            with ContextService.without_telemetry(args.project, args.state_dir) as svc:
                for verdict, ids in (("confirmed", args.confirm), ("rejected", args.reject)):
                    for finding_id in ids:
                        svc.review_finding(finding_id, verdict)
                findings = list(svc.store.iter_findings())
                for f in findings:
                    print(f"## {f.finding_id}  {f.source.label()}  [{f.review}, {f.agent_id}, "
                          f"{f.source.ingested_at}]\n{f.claim}\n> {f.evidence}\n")  # fmt: skip
                print(f"{len(findings)} finding(s)")
            return 0

        if args.command == "ingest":
            with ContextService(
                args.project, args.state_dir, retrieval=args.retrieval, embedder=_embedder(args)
            ) as svc:
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
                            "chunks_embedded": report.chunks_embedded,
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
                "hops": args.hops,
                "detail": args.detail,
                "agent_id": args.agent_id,
            }
        else:
            print("error: give --task or --request-file", file=sys.stderr)
            return 2
        request = ContextRequest.from_dict(data)
        with ContextService(
            args.project,
            args.state_dir,
            record_task_text=args.record_task_text,
            retrieval=args.retrieval,
            embedder=_embedder(args),
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
