from pathlib import Path

import pytest

from context_orchestrator.memory.store import MemoryStore


def test_ingest_is_incremental(project: Path, tmp_path: Path) -> None:
    with MemoryStore(tmp_path / "m.db") as store:
        first = store.ingest(project)
        assert len(first.added) == 18 and not first.updated
        total = store.count_chunks()

        second = store.ingest(project)
        assert not second.added and not second.updated and len(second.unchanged) == 18
        assert store.count_chunks() == total

        (project / "docs" / "conventions.md").write_text(
            "---\nkind: convention\nstatus: verified\n---\n# Conventions\n\nUse tabs.\n",
            encoding="utf-8",
        )
        (project / "README.md").unlink()
        third = store.ingest(project)
        assert third.updated == ["docs/conventions.md"]
        assert third.removed == ["README.md"]
        paths = {c.source.path for c in store.iter_chunks()}
        assert "README.md" not in paths
        fts_rows = store.conn.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0]
        assert fts_rows == store.count_chunks()  # no orphaned index rows


def test_ingest_never_writes_to_the_project(project: Path, tmp_path: Path) -> None:
    before = {p: p.stat().st_mtime_ns for p in project.rglob("*")}
    with MemoryStore(tmp_path / "m.db") as store:
        store.ingest(project)
    after = {p: p.stat().st_mtime_ns for p in project.rglob("*")}
    assert before == after


def test_store_refuses_a_second_project(project: Path, tmp_path: Path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    (other / "a.md").write_text("# A")
    with MemoryStore(tmp_path / "m.db") as store:
        store.ingest(project)
        with pytest.raises(ValueError, match="belongs to project"):
            store.ingest(other)


def test_chunks_carry_provenance(project: Path, tmp_path: Path) -> None:
    with MemoryStore(tmp_path / "m.db") as store:
        store.ingest(project)
        for chunk in store.iter_chunks():
            lines = (project / chunk.source.path).read_text(encoding="utf-8").splitlines()
            assert chunk.text == "\n".join(
                lines[chunk.source.line_start - 1 : chunk.source.line_end]
            )
            assert len(chunk.source.file_sha256) == 64
