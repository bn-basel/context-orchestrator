from pathlib import Path

from context_orchestrator.memory.loader import (
    discover_files,
    infer_kind,
    load_file,
    parse_front_matter,
)
from context_orchestrator.models import InfoKind, Status


def test_front_matter_is_parsed_and_measured() -> None:
    lines = ["---", "kind: decision", "status: verified", "---", "# Title"]
    meta, consumed = parse_front_matter(lines)
    assert meta == {"kind": "decision", "status": "verified"}
    assert consumed == 4


def test_unterminated_front_matter_is_ignored() -> None:
    assert parse_front_matter(["---", "kind: decision", "# Title"]) == ({}, 0)


def test_kind_inference_rules() -> None:
    assert infer_kind(Path("tests/test_x.py"), {}) is InfoKind.TEST
    assert infer_kind(Path("db/schema.sql"), {}) is InfoKind.SCHEMA
    assert infer_kind(Path("pyproject.toml"), {}) is InfoKind.DEPENDENCY
    assert infer_kind(Path("src/app/x.py"), {}) is InfoKind.CODE
    assert infer_kind(Path("docs/adr/0001.md"), {}) is InfoKind.DECISION
    assert infer_kind(Path("docs/notes.md"), {}) is InfoKind.DOC
    # Front matter wins over the path; unknown values fall back to the path.
    assert infer_kind(Path("docs/notes.md"), {"kind": "constraint"}) is InfoKind.CONSTRAINT
    assert infer_kind(Path("docs/notes.md"), {"kind": "nonsense"}) is InfoKind.DOC


def test_markdown_sections_keep_exact_line_ranges(project: Path) -> None:
    path = project / "docs" / "decisions" / "0004-store-money-as-integer-cents.md"
    loaded = load_file(project, path)
    assert loaded is not None
    assert loaded.kind is InfoKind.DECISION and loaded.status is Status.VERIFIED
    assert loaded.metadata["supersedes"] == "0002"
    file_lines = path.read_text(encoding="utf-8").splitlines()
    for chunk in loaded.chunks:
        assert chunk.text == "\n".join(file_lines[chunk.line_start - 1 : chunk.line_end])
    headings = [c.heading for c in loaded.chunks]
    assert "ADR 0004: Store money as integer cents > Decision" in headings


def test_python_is_split_per_top_level_definition(project: Path) -> None:
    loaded = load_file(project, project / "src" / "shelfwise" / "loans.py")
    assert loaded is not None
    headings = [c.heading for c in loaded.chunks]
    assert headings[0].endswith("(module header)")
    assert "src/shelfwise/loans.py::days_overdue" in headings
    # The decorator line belongs to the class chunk.
    loan_chunk = next(c for c in loaded.chunks if c.heading.endswith("::Loan"))
    assert loan_chunk.text.startswith("@dataclass")
    assert loaded.status is Status.OBSERVED


def test_sql_is_split_per_create_statement(project: Path) -> None:
    loaded = load_file(project, project / "db" / "schema.sql")
    assert loaded is not None
    headings = [c.heading for c in loaded.chunks]
    assert "db/schema.sql::CREATE TABLE loans" in headings
    assert "db/schema.sql::CREATE INDEX loans_member_active ON loans" in headings


def test_discovery_skips_state_and_cache_dirs(tmp_path: Path) -> None:
    (tmp_path / ".ctxo").mkdir()
    (tmp_path / ".ctxo" / "x.md").write_text("# hidden")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "x.py").write_text("x = 1")
    (tmp_path / "keep.md").write_text("# kept")
    (tmp_path / "image.png").write_bytes(b"\x89PNG")
    assert [p.name for p in discover_files(tmp_path)] == ["keep.md"]


def test_long_files_are_windowed(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("\n".join(f"line {i}" for i in range(1, 201)))
    loaded = load_file(tmp_path, tmp_path / "notes.txt")
    assert loaded is not None
    assert [(c.line_start, c.line_end) for c in loaded.chunks] == [
        (1, 60),
        (61, 120),
        (121, 180),
        (181, 200),
    ]


def test_heading_without_body_is_folded_into_next_section(project: Path) -> None:
    path = project / "docs" / "decisions" / "0004-store-money-as-integer-cents.md"
    loaded = load_file(project, path)
    assert loaded is not None
    first = loaded.chunks[0]
    assert first.heading == "ADR 0004: Store money as integer cents > Context"
    assert first.text.startswith("# ADR 0004")
    assert "## Context" in first.text
