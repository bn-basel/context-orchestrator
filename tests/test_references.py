from pathlib import Path

import pytest

from context_orchestrator.agent_interface.api import ContextService
from context_orchestrator.models import ContextRequest, InfoKind, SourceRef
from context_orchestrator.retrieval.references import ReferenceIndex


@pytest.fixture
def svc(tmp_path: Path):
    root = tmp_path / "proj"
    (root / "docs").mkdir(parents=True)
    (root / "src" / "app").mkdir(parents=True)
    (root / "docs" / "issues.md").write_text(
        "---\nkind: known_issue\nstatus: verified\n---\n"
        "# Issues\n\n## ISSUE-7: invoices total wrong\n"
        "The invoice total is wrong because `ledger.accumulate()` drops the last line.\n"
        "Also see handle(), get() and run_all().\n",
        encoding="utf-8",
    )
    (root / "src" / "app" / "ledger.py").write_text(
        "def accumulate(lines):\n    return sum(lines[:-1])\n\n\ndef handle(x):\n    return x\n",
        encoding="utf-8",
    )
    (root / "src" / "app" / "other.py").write_text(
        "def accumulate(xs):\n    return xs\n\n\n"
        "class Runner:\n    def run_all(self):\n        pass\n\n    def get(self):\n        pass\n",
        encoding="utf-8",
    )
    (root / "src" / "app" / "third.py").write_text(
        "def handle(y):\n    return y\n", encoding="utf-8"
    )
    (root / "src" / "app" / "fourth.py").write_text(
        "def handle(z):\n    return z\n", encoding="utf-8"
    )
    service = ContextService.without_telemetry(root, tmp_path / "state")
    service.ingest()
    yield service
    service.close()


def _issue_chunk(svc: ContextService):
    return next(
        c for c in svc.store.iter_chunks() if c.heading.endswith("ISSUE-7: invoices total wrong")
    )


def test_reference_rules(svc: ContextService) -> None:
    refs = ReferenceIndex(svc.store).references_in(_issue_chunk(svc))
    found = {(r.name, r.chunk.source.path) for r in refs}
    # module.name prefers the file named after the module, even with two definitions.
    assert ("accumulate", "src/app/ledger.py") in found
    # A method inside a class is a definition too.
    assert ("run_all", "src/app/other.py") in found
    # Too short ("get") and too ambiguous ("handle", defined three times) are not followed.
    assert {r.name for r in refs} == {"accumulate", "run_all"}


def test_references_are_added_when_enabled(svc: ContextService) -> None:
    base = dict(task="ISSUE-7 invoice total wrong", kinds=[InfoKind.KNOWN_ISSUE, InfoKind.CODE])
    off = svc.request(ContextRequest(**base, max_references=0))
    on = svc.request(ContextRequest(**base, max_references=4))
    assert not any(i.via for i in off.items)
    referenced = [i for i in on.items if i.via]
    assert {i.source.path for i in referenced} == {"src/app/ledger.py", "src/app/other.py"}
    assert all("named in docs/issues.md" in (i.via or "") for i in referenced)
    assert "references: `accumulate`" in on.render_markdown()


def test_references_respect_requested_kinds_and_limit(svc: ContextService) -> None:
    only_issues = svc.request(
        ContextRequest(task="ISSUE-7 invoice total wrong", kinds=[InfoKind.KNOWN_ISSUE],
                       max_references=4)
    )  # fmt: skip
    assert not any(i.via for i in only_issues.items)
    one = svc.request(
        ContextRequest(task="ISSUE-7 invoice total wrong", kinds=[InfoKind.KNOWN_ISSUE,
                       InfoKind.CODE], max_references=1)
    )  # fmt: skip
    assert sum(1 for i in one.items if i.via) <= 1


def test_chunk_by_source(svc: ContextService) -> None:
    chunk = _issue_chunk(svc)
    assert svc.store.chunk_by_source(chunk.source) == chunk
    missing = SourceRef("nope.md", 1, 2, "0" * 64, "x")
    assert svc.store.chunk_by_source(missing) is None


def test_references_are_not_followed_from_code(svc: ContextService) -> None:
    # ledger.py's chunks call nothing followable, but other.py's class is code too: code
    # items never pull in further code, only documents do.
    package = svc.request(
        ContextRequest(task="accumulate lines run_all", kinds=[InfoKind.CODE], max_references=4)
    )
    assert package.items and not any(i.via for i in package.items)
