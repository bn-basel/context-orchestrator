from pathlib import Path

import pytest

from context_orchestrator.agent_interface.api import ContextService
from context_orchestrator.models import ContextRequest, InfoKind
from context_orchestrator.retrieval.lexical import ScoredChunk
from context_orchestrator.retrieval.multihop import as_phrase, expansion_names, fuse
from context_orchestrator.retrieval.references import ReferenceIndex, mentioned_names

TASK = "Invoice totals are short for some clubs"


@pytest.fixture
def svc(tmp_path: Path):
    root = tmp_path / "proj"
    for d in ("docs", "src/app", "tests", "db"):
        (root / d).mkdir(parents=True)
    (root / "docs" / "issues.md").write_text(
        "---\nkind: known_issue\nstatus: verified\n---\n"
        "# Issues\n\n## ISSUE-7: invoice totals short for some clubs\n"
        "Caused by `ledger.accumulate()`; it also writes to `ledger_entries`.\n",
        encoding="utf-8",
    )
    (root / "src" / "app" / "ledger.py").write_text(
        "def accumulate(lines):\n    return sum(lines[:-1])\n", encoding="utf-8"
    )
    (root / "tests" / "test_ledger.py").write_text(
        "from app.ledger import accumulate\n\n\ndef test_accumulate_keeps_every_line():\n"
        "    assert accumulate([1, 2, 3]) == 6\n",
        encoding="utf-8",
    )
    (root / "db" / "schema.sql").write_text(
        "CREATE TABLE ledger_entries (\n    id INTEGER PRIMARY KEY\n);\n", encoding="utf-8"
    )
    service = ContextService.without_telemetry(root, tmp_path / "state")
    service.ingest()
    yield service
    service.close()


def test_mentioned_names_and_phrases() -> None:
    text = "def outer():\n    `ledger.accumulate()` then run_all(x) and core.tz.to_utc"
    # Module names before a dot ("ledger", "core") are not mentions; what follows is.
    assert mentioned_names(text) == ["outer", "accumulate", "run_all", "tz", "to_utc"]
    assert as_phrase("occurrence_windows") == "occurrence windows"


def test_expansion_keeps_real_and_specific_names(svc: ContextService) -> None:
    refs = ReferenceIndex(svc.store)
    issue = next(c for c in svc.store.iter_chunks() if c.source.path == "docs/issues.md")
    # "ledger" is not a definition, "accumulate" is; "ledger_entries" is a specific table.
    assert expansion_names([issue], refs) == ["accumulate", "ledger_entries"]


def test_two_hops_reach_code_and_tests_the_task_never_names(svc: ContextService) -> None:
    kinds = [InfoKind.KNOWN_ISSUE, InfoKind.CODE, InfoKind.TEST, InfoKind.SCHEMA]
    one = svc.request(ContextRequest(task=TASK, kinds=kinds, hops=1))
    two = svc.request(ContextRequest(task=TASK, kinds=kinds, hops=2))
    assert {i.source.path for i in one.items} == {"docs/issues.md"}
    found = {i.source.path: i for i in two.items}
    assert {"src/app/ledger.py", "tests/test_ledger.py", "db/schema.sql"} <= set(found)
    assert "follow-up search" in (found["src/app/ledger.py"].via or "")
    assert found["docs/issues.md"].via is None  # found by the first search
    assert "follow-up search" in two.render_markdown()


def test_fuse_marks_only_follow_up_hits(svc: ContextService) -> None:
    chunks = list(svc.store.iter_chunks())
    a, b = ScoredChunk(chunks[0], 5.0, ("x",)), ScoredChunk(chunks[1], 4.0, ("y",))
    fused = fuse([a], [b, a], ["name"])
    assert fused[0].chunk == a.chunk and fused[0].via is None  # in both lists: ranks first
    assert fused[1].via and "`name`" in fused[1].via
