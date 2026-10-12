import gzip
import json
from pathlib import Path

import pytest

from context_orchestrator.evaluation import own_loop
from context_orchestrator.evaluation.own_loop import (
    LocalTools,
    LoopConfig,
    PrunePolicy,
    Turn,
    prune,
    run_loop,
)
from context_orchestrator.evaluation.retrieval_eval import load_suite

REPO = Path(__file__).resolve().parents[1]
HALLPASS = REPO / "benchmarks" / "tasks" / "hallpass.json"
HALLPASS_RUBRICS = REPO / "benchmarks" / "tasks" / "hallpass.rubrics.json"
ANSWER = (
    "occurrence_windows adds weeks in UTC; step the local date and use local_to_utc. "
    "Risk: extend_series and the strict xfail tests."
)
USAGE = {
    "input_tokens": 100,
    "output_tokens": 50,
    "cache_creation_input_tokens": 1000,
    "cache_read_input_tokens": 2000,
}


@pytest.fixture
def project(tmp_path: Path) -> Path:
    dest = tmp_path / "proj"
    (dest / "src").mkdir(parents=True)
    (dest / "src" / "a.py").write_text("def alpha():\n    return 1\n# beta here\n", "utf-8")
    (dest / "docs.md").write_text("Beta is documented.\n", "utf-8")
    return dest


def test_tools_read_grep_glob_and_confinement(project: Path) -> None:
    tools = LocalTools(project)
    text, err = tools.run("read_file", {"path": "src/a.py", "offset": 2, "limit": 1})
    assert not err and text.startswith("     2\t    return 1") and "showing 2-2" in text
    text, _ = tools.run("grep", {"pattern": "beta", "ignore_case": True})
    assert text.splitlines() == ["docs.md:1: Beta is documented.", "src/a.py:3: # beta here"]
    text, _ = tools.run("grep", {"pattern": "beta", "ignore_case": True, "glob": "*.py"})
    assert text == "src/a.py:3: # beta here"
    assert tools.run("glob", {"pattern": "**/*.py"}) == ("src/a.py", False)
    assert tools.run("read_file", {"path": "../outside.txt"})[1] is True
    assert tools.run("request_context", {"task": "x"})[1] is True  # no service in this arm


def _messages(sizes: list[int]) -> list[dict]:
    msgs: list[dict] = [{"role": "user", "content": [{"type": "text", "text": "task"}]}]
    for i, size in enumerate(sizes):
        msgs.append({"role": "assistant", "content": [
            {"type": "tool_use", "id": f"t{i}", "name": "read_file", "input": {"path": f"f{i}"}}
        ]})  # fmt: skip
        msgs.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": f"t{i}", "content": "x" * size}
        ]})  # fmt: skip
    return msgs


def _results(msgs: list[dict]) -> list[str]:
    return [b["content"] for m in msgs for b in m["content"] if b["type"] == "tool_result"]


def test_prune_clears_all_but_the_recent_results_once_over_the_trigger() -> None:
    policy = PrunePolicy(trigger_tokens=1000, keep=2, min_clear_tokens=500)
    small = _messages([400, 400])
    assert prune(small, policy) is None  # under the trigger: untouched

    msgs = _messages([4000, 4000, 4000, 4000])
    event = prune(msgs, policy)
    assert event is not None and event["cleared_results"] == 2
    results = _results(msgs)
    assert results[0].startswith('[read_file {"path": "f0"}: result cleared')
    assert results[2] == "x" * 4000 and results[3] == "x" * 4000
    assert prune(msgs, policy) is None  # cleared results no longer count


def test_prune_skips_when_too_little_would_go() -> None:
    policy = PrunePolicy(trigger_tokens=1000, keep=1, min_clear_tokens=5000)
    msgs = _messages([40, 40, 40000])
    assert prune(msgs, policy) is None


def test_cache_mark_on_last_block_only_and_private_keys_dropped() -> None:
    msgs = _messages([10])
    msgs[2]["content"][0]["_cleared"] = True
    marked = own_loop._with_cache_marks(msgs)
    assert marked[-1]["content"][-1]["cache_control"] == {"type": "ephemeral"}
    assert "_cleared" not in marked[-1]["content"][-1]
    assert "cache_control" not in msgs[-1]["content"][-1]  # stored transcript unchanged
    assert all("cache_control" not in b for m in marked[:-1] for b in m["content"])


class ScriptedModel:
    """Reads files until it has made `reads` tool calls, records a finding when it can,
    then answers. Records every request it was sent."""

    def __init__(self, project: Path, reads: int = 2, finding: dict | None = None) -> None:
        self.project = project
        self.reads = reads
        self.finding = finding
        self.requests: list[dict] = []

    def __call__(self, **kwargs) -> Turn:
        self.requests.append(json.loads(json.dumps(kwargs)))
        names = {t["name"] for t in kwargs["tools"]}
        done = [
            b["name"] for m in kwargs["messages"] for b in m["content"] if b["type"] == "tool_use"
        ]
        n = len(self.requests)
        if "request_context" in names and "request_context" not in done:
            use = {"name": "request_context", "input": {"task": "clocks change block booking"}}
        elif done.count("read_file") < self.reads:
            use = {"name": "read_file", "input": {"path": "src/hallpass/bookings/recurring.py"}}
        elif "record_finding" in names and self.finding and "record_finding" not in done:
            use = {"name": "record_finding", "input": self.finding}
        else:
            return Turn(f"gen-{n}", "end_turn", [{"type": "text", "text": ANSWER}], dict(USAGE))
        thinking = {"type": "thinking", "thinking": "", "signature": f"sig{n}"}
        block = {"type": "tool_use", "id": f"tu{n}", **use}
        return Turn(f"gen-{n}", "tool_use", [thinking, block], dict(USAGE))


def test_run_loop_returns_answer_usage_and_prunes(tmp_path: Path) -> None:
    project = HALLPASS.parent / "../corpora/hallpass"
    model = ScriptedModel(project, reads=4)
    config = LoopConfig(prune=PrunePolicy(trigger_tokens=100, keep=1, min_clear_tokens=10))
    result = run_loop(model, config, "LP", "task", LocalTools(project.resolve()))
    assert result["answer"] == ANSWER and result["error"] is None
    assert result["tool_calls"] == ["read_file"] * 4
    assert result["prune_events"]  # the repeated big reads were cleared
    last_sent = model.requests[-1]["messages"]
    cleared = [b for m in last_sent for b in m["content"] if b["type"] == "tool_result"]
    assert "result cleared" in cleared[0]["content"] and "cleared" not in cleared[-1]["content"]
    # Thinking blocks are passed back, except after the first edited message: there they
    # would no longer match the history they were made with.
    assert model.requests[1]["messages"][1]["content"][0]["type"] == "thinking"
    first_edit = next(
        i for i, m in enumerate(last_sent)
        if any("result cleared" in str(b.get("content", "")) for b in m["content"])
    )  # fmt: skip
    after = [b["type"] for m in last_sent[first_edit:] for b in m["content"]]
    assert "thinking" not in after and "tool_use" in after
    assert last_sent[1]["content"][0]["type"] == "thinking"  # before the edit: kept
    assert sum(e["thinking_blocks_dropped"] for e in result["prune_events"]) >= 1
    usage = own_loop.summarise_usage(result["calls"], config.model)
    assert usage["total_input_tokens"]["value"] == 5 * 3100
    assert usage["estimated_cost_usd"]["kind"] == "estimated"
    assert usage["measured_cost_usd"]["kind"] == "unavailable"  # never looked up here


def test_cost_estimate_uses_the_prompt_size_rate_card() -> None:
    model = "anthropic/claude-haiku-5.5"
    small = {"input_tokens": 1000, "cache_read_input_tokens": 50_000,
             "cache_creation_input_tokens": 0, "output_tokens": 1000}  # fmt: skip
    assert own_loop.estimate_cost(model, small) == pytest.approx(
        (1000 * 0.10 + 50_000 * 0.01 + 1000 * 0.50) / 1e6
    )
    large = {**small, "cache_read_input_tokens": 150_000}  # prompt over 100k: second card
    assert own_loop.estimate_cost(model, large) == pytest.approx(
        (1000 * 0.50 + 150_000 * 0.05 + 1000 * 2.50) / 1e6
    )
    assert own_loop.estimate_cost("anthropic/unknown", small) is None


def test_charge_reported_in_the_usage_is_the_measured_cost() -> None:
    def model(**kwargs) -> Turn:
        usage = {**USAGE, "cost": 0.0002}
        return Turn("msg_1", "end_turn", [{"type": "text", "text": "done"}], usage)

    project = (HALLPASS.parent / "../corpora/hallpass").resolve()
    result = run_loop(model, LoopConfig(), "L", "t", LocalTools(project))
    usage = own_loop.summarise_usage(result["calls"], LoopConfig().model)
    assert usage["measured_cost_usd"] == {
        "value": 0.0002, "kind": "measured", "method": "OpenRouter's reported charge per call"
    }  # fmt: skip


def test_refusal_ends_the_run_with_an_error() -> None:
    def model(**kwargs) -> Turn:
        return Turn("gen-1", "refusal", [], dict(USAGE))

    project = (HALLPASS.parent / "../corpora/hallpass").resolve()
    result = run_loop(model, LoopConfig(), "L", "t", LocalTools(project))
    assert "refusal" in result["error"] and result["answer"] == ""


def test_run_loop_budget_brake() -> None:
    project = (HALLPASS.parent / "../corpora/hallpass").resolve()
    config = LoopConfig(max_total_usd=0.001)
    result = run_loop(ScriptedModel(project, reads=10), config, "L", "t", LocalTools(project))
    assert result["error"].startswith("stopped: experiment budget")


def test_prune_experiment_end_to_end(tmp_path: Path) -> None:
    suite = load_suite(HALLPASS)
    rubrics = own_loop.rubrics_for(HALLPASS_RUBRICS, suite)
    jobs = own_loop.plan_prune(suite, rubrics, ["L", "LP"], 1, ["H01"], seed=1)
    model = ScriptedModel(suite.project)
    run_dir = own_loop.run_experiment(
        "prune", jobs, suite.project, tmp_path / "out", tmp_path / "work", LoopConfig(), {},
        model=model, cost_lookup=lambda gen_id: 0.001, key_status=lambda: {"limit": 5},
    )  # fmt: skip
    records = [json.loads(x) for x in (run_dir / "runs.jsonl").read_text("utf-8").splitlines()]
    assert {r["arm"] for r in records} == {"L", "LP"}
    assert all(r["grade"]["score"] == 1.0 for r in records)
    assert records[0]["usage"]["measured_cost_usd"]["value"] == pytest.approx(0.003)
    meta = json.loads((run_dir / "run.json").read_text("utf-8"))
    assert meta["summary"]["pairs"]["LP vs L"]["tasks"] == 1
    assert meta["key_status_before"] == {"limit": 5}
    raw = json.loads(gzip.decompress((run_dir / "raw" / "H01-L-task-0.json.gz").read_bytes()))
    assert raw["messages"][0]["role"] == "user"
    assert "| LP vs L | 1 |" in (run_dir / "summary.md").read_text("utf-8")


def test_memory_experiment_follow_up_sees_parent_findings(tmp_path: Path) -> None:
    corpus = (HALLPASS.parent / "../corpora/hallpass").resolve()
    lines = (corpus / "docs/known-issues/bookings.md").read_text("utf-8").splitlines()
    data = json.loads(HALLPASS.read_text("utf-8"))
    follow = {**next(t for t in data["tasks"] if t["id"] == "H01"), "id": "F01", "after": "H01"}
    followups = tmp_path / "followups.json"
    followups.write_text(json.dumps({**data, "project": str(corpus), "tasks": [follow]}), "utf-8")
    rubric_data = json.loads(HALLPASS_RUBRICS.read_text("utf-8"))
    f_rubrics = tmp_path / "followups.rubrics.json"
    f_rubrics.write_text(
        json.dumps({**rubric_data, "rubrics": {"F01": rubric_data["rubrics"]["H01"]}}), "utf-8"
    )  # noqa: E501

    parents = load_suite(HALLPASS)
    suite = load_suite(followups)
    jobs = own_loop.plan_memory(
        suite, own_loop.rubrics_for(f_rubrics, suite), parents,
        own_loop.rubrics_for(HALLPASS_RUBRICS, parents), own_loop.load_followups(followups),
        1, None, seed=3,
    )  # fmt: skip
    roles = [(j.task.id, j.arm, j.role) for j in jobs]
    assert roles.index(("H01", "SM", "parent")) < roles.index(("F01", "SM", "task"))
    assert ("F01", "SM0", "task") in roles

    finding = {
        "claim": "Block bookings drift an hour after the clocks change: "
        "occurrence_windows adds weeks in UTC.",
        "path": "docs/known-issues/bookings.md",
        "line_start": 67,
        "line_end": 69,
        "evidence": lines[66].strip()[:60],
    }
    model = ScriptedModel(corpus, reads=1, finding=finding)
    run_dir = own_loop.run_experiment(
        "memory", jobs, corpus, tmp_path / "out", tmp_path / "work", LoopConfig(), {},
        model=model, cost_lookup=None, key_status=None,
    )  # fmt: skip
    records = {
        (r["task_id"], r["arm"], r["role"]): r
        for r in map(json.loads, (run_dir / "runs.jsonl").read_text("utf-8").splitlines())
    }
    assert records[("H01", "SM", "parent")]["findings_after"] == 1
    assert records[("F01", "SM", "task")]["findings_before"] == 1
    assert records[("F01", "SM0", "task")]["findings_before"] == 0
    meta = json.loads((run_dir / "run.json").read_text("utf-8"))
    assert meta["summary"]["parent_runs"]["findings_recorded"] == [1]
    assert "SM vs SM0" in meta["summary"]["pairs"]
    # The finding reached the follow-up agent through request_context.
    raw = json.loads(gzip.decompress((run_dir / "raw" / "F01-SM-task-0.json.gz").read_bytes()))
    served = raw["messages"][2]["content"][0]["content"]
    assert "Finding: Block bookings drift an hour after the clocks change" in served


def test_key_comes_from_env_var_first_then_env_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    monkeypatch.setattr(own_loop, "ENV_FILE", env_file)
    monkeypatch.delenv(own_loop.KEY_ENV, raising=False)
    assert own_loop.read_key() is None  # no file
    env_file.write_text("# comment\nOTHER=x\nOPENROUTER_API_KEY=\n", "utf-8")
    assert own_loop.read_key() is None  # present but empty
    env_file.write_text('OPENROUTER_API_KEY = "sk-or-test"\n', "utf-8")
    assert own_loop.read_key() == "sk-or-test"
    monkeypatch.setenv(own_loop.KEY_ENV, "from-env")
    assert own_loop.read_key() == "from-env"


def test_no_key_gives_a_clear_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv(own_loop.KEY_ENV, raising=False)
    monkeypatch.setattr(own_loop, "ENV_FILE", tmp_path / "missing.env")  # ignore a real .env
    assert own_loop.openrouter_key_status() is None  # no request is made without a key
    assert own_loop.openrouter_generation_cost("gen-1") is None
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY|Anthropic SDK"):
        own_loop.openrouter_model()


def test_compact_reads_return_an_outline_for_long_files(tmp_path: Path) -> None:
    project = tmp_path / "p"
    project.mkdir()
    body = ["# Title", "intro"] + [f"x = {i}" for i in range(200)]
    body[120] = "def important():"
    body[150] = "## Later section"
    (project / "long.py").write_text("\n".join(body), "utf-8")
    (project / "short.py").write_text("a = 1\nb = 2\n", "utf-8")
    compact = LocalTools(project, compact_reads=True)
    text, err = compact.run("read_file", {"path": "long.py"})
    assert not err and "only its outline is shown" in text
    assert "   121\tdef important():" in text and "   151\t## Later section" in text
    assert "x = 100" not in text  # the body is not shown
    assert "x = 100" in compact.run("read_file", {"path": "long.py", "offset": 100})[0]
    assert compact.run("read_file", {"path": "short.py"})[0].startswith("     1\ta = 1")
    assert "outline" not in LocalTools(project).run("read_file", {"path": "long.py"})[0]
    lc_read = own_loop.tools_for("LC")[0]
    assert "outline" in lc_read["description"] and "outline" not in TOOLS_READ_DESCRIPTION


TOOLS_READ_DESCRIPTION = own_loop.TOOLS[0]["description"]


def test_low_effort_arm_sends_low_effort() -> None:
    sent = []

    def model(**kwargs) -> Turn:
        sent.append(kwargs["output_config"]["effort"])
        return Turn("m", "end_turn", [{"type": "text", "text": "ok"}], dict(USAGE))

    project = (HALLPASS.parent / "../corpora/hallpass").resolve()
    run_loop(model, LoopConfig(), "LE", "t", LocalTools(project))
    run_loop(model, LoopConfig(), "L", "t", LocalTools(project))
    assert sent == ["low", "medium"]


def test_trust_experiment_seeds_reviewed_findings(tmp_path: Path) -> None:
    corpus = (HALLPASS.parent / "../corpora/hallpass").resolve()
    followups = load_suite(REPO / "benchmarks/tasks/hallpass_followups.json")
    rubrics = own_loop.rubrics_for(
        REPO / "benchmarks/tasks/hallpass_followups.rubrics.json", followups
    )
    seeds = own_loop.trust_seeds(REPO / "benchmarks/tasks/hallpass_followups.findings.json")
    assert len(seeds["trusted"]) == len(seeds["untrusted"]) == 16
    jobs = own_loop.plan_trust(followups, rubrics, 1, ["F05"], seed=1)
    assert sorted(j.arm for j in jobs) == ["T0", "TR", "TU"]
    assert own_loop.system_prompt("TU") == own_loop.system_prompt("T0")
    assert "rely on them" in own_loop.system_prompt("TR")
    model = ScriptedModel(corpus, reads=0)
    run_dir = own_loop.run_experiment(
        "trust", jobs, corpus, tmp_path / "out", tmp_path / "work", LoopConfig(), {},
        model=model, cost_lookup=None, key_status=None, seeds=seeds,
    )  # fmt: skip
    served = {}
    for p in (run_dir / "raw").glob("*.json.gz"):
        raw = json.loads(gzip.decompress(p.read_bytes()))
        served[p.name.split("-")[1]] = raw["messages"][2]["content"][0]["content"]
    assert "_[finding, verified" in served["TR"]
    assert "_[finding, unverified" in served["TU"]
    assert "Finding:" not in served["T0"]
