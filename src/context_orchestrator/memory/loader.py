"""Discover project files and split them into retrievable chunks.

Every rule here is deliberately simple and explainable:

* Markdown is split at level-1 and level-2 headings. Front matter (``---``
  delimited ``key: value`` lines) can declare ``kind`` and ``status``.
* Python is split at top-level ``def``/``class`` statements using ``ast``.
* SQL is split at ``CREATE`` statements.
* Anything else, and any chunk longer than ``MAX_CHUNK_LINES``, is split into
  fixed line windows.

Line numbers always refer to the original file (1-based, inclusive).
"""

from __future__ import annotations

import ast
import hashlib
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from context_orchestrator.models import InfoKind, Status

log = logging.getLogger(__name__)

INCLUDE_SUFFIXES = {".md", ".py", ".sql", ".toml", ".txt", ".cfg", ".ini", ".json", ".yaml", ".yml"}
EXCLUDE_DIRS = {
    ".git",
    ".hg",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".ctxo",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
}
MAX_FILE_BYTES = 512 * 1024
MAX_CHUNK_LINES = 80
WINDOW_LINES = 60

CODE_SUFFIXES = {".py", ".js", ".ts", ".tsx", ".go", ".rs", ".java", ".rb", ".cs"}
DEPENDENCY_FILES = {
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "setup.cfg",
    "package.json",
    "cargo.toml",
    "go.mod",
    "gemfile",
}
DECISION_DIRS = {"decisions", "adr", "adrs"}

_HEADING = re.compile(r"^(#{1,2})\s+(.+?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_SQL_CREATE = re.compile(r"^\s*CREATE\s+", re.IGNORECASE)


@dataclass(slots=True)
class RawChunk:
    heading: str
    text: str
    line_start: int
    line_end: int


@dataclass(slots=True)
class LoadedFile:
    path: str  # POSIX, relative to project root
    sha256: str
    kind: InfoKind
    status: Status
    chunks: list[RawChunk]
    metadata: dict[str, str] = field(default_factory=dict)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def discover_files(root: Path) -> Iterator[Path]:
    """Yield candidate files under ``root`` in a stable order."""
    for path in sorted(root.rglob("*")):
        rel_parts = path.relative_to(root).parts
        if any(part in EXCLUDE_DIRS for part in rel_parts[:-1]):
            continue
        if path.is_file() and path.suffix.lower() in INCLUDE_SUFFIXES:
            yield path


def parse_front_matter(lines: list[str]) -> tuple[dict[str, str], int]:
    """Return (front matter dict, number of lines it occupies)."""
    if not lines or lines[0].strip() != "---":
        return {}, 0
    meta: dict[str, str] = {}
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return meta, i + 1
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip().lower()] = value.strip().strip("\"'")
    return {}, 0  # unterminated: treat as ordinary text


def infer_kind(rel_path: Path, front_matter: dict[str, str]) -> InfoKind:
    declared = front_matter.get("kind")
    if declared:
        try:
            return InfoKind(declared.lower())
        except ValueError:
            log.warning(
                "%s: unknown kind %r in front matter, inferring from path", rel_path, declared
            )
    name = rel_path.name.lower()
    dirs = {p.lower() for p in rel_path.parts[:-1]}
    if "tests" in dirs or "test" in dirs or name.startswith("test_") or name.endswith("_test.py"):
        return InfoKind.TEST
    if rel_path.suffix.lower() == ".sql":
        return InfoKind.SCHEMA
    if name in DEPENDENCY_FILES:
        return InfoKind.DEPENDENCY
    if rel_path.suffix.lower() in CODE_SUFFIXES:
        return InfoKind.CODE
    if rel_path.suffix.lower() == ".md" and dirs & DECISION_DIRS:
        return InfoKind.DECISION
    return InfoKind.DOC


def infer_status(rel_path: Path, front_matter: dict[str, str]) -> Status:
    declared = front_matter.get("status")
    if declared:
        try:
            return Status(declared.lower())
        except ValueError:
            log.warning("%s: unknown status %r, treating as unverified", rel_path, declared)
            return Status.UNVERIFIED
    return Status.UNVERIFIED if rel_path.suffix.lower() == ".md" else Status.OBSERVED


def _make_chunk(heading: str, lines: list[str], start: int, end: int) -> RawChunk | None:
    """Build a chunk from 1-based inclusive [start, end], trimming blank edges."""
    while start <= end and not lines[start - 1].strip():
        start += 1
    while end >= start and not lines[end - 1].strip():
        end -= 1
    if start > end:
        return None
    return RawChunk(heading, "\n".join(lines[start - 1 : end]), start, end)


def _split_at(
    lines: list[str], boundaries: list[tuple[int, str]], first_heading: str, body_start: int = 1
) -> list[RawChunk]:
    """Split lines at 1-based boundary lines; text before the first is its own chunk."""
    chunks: list[RawChunk] = []
    points = [b for b in boundaries if b[0] >= body_start]
    if not points or points[0][0] > body_start:
        points.insert(0, (body_start, first_heading))
    for i, (start, heading) in enumerate(points):
        end = points[i + 1][0] - 1 if i + 1 < len(points) else len(lines)
        chunk = _make_chunk(heading, lines, start, end)
        if chunk:
            chunks.append(chunk)
    return chunks


def _window(chunk: RawChunk) -> list[RawChunk]:
    lines = chunk.text.split("\n")
    if len(lines) <= MAX_CHUNK_LINES:
        return [chunk]
    out = []
    for offset in range(0, len(lines), WINDOW_LINES):
        part = lines[offset : offset + WINDOW_LINES]
        start = chunk.line_start + offset
        out.append(
            RawChunk(
                f"{chunk.heading} (part {offset // WINDOW_LINES + 1})",
                "\n".join(part),
                start,
                start + len(part) - 1,
            )
        )
    return out


def chunk_markdown(rel: str, lines: list[str], body_start: int, title: str) -> list[RawChunk]:
    """Split at # and ## headings; ## sections are labelled 'Document title > Section'."""
    boundaries: list[tuple[int, str]] = []
    in_fence = False
    doc_title = ""
    for n, line in enumerate(lines, start=1):
        if n < body_start:
            continue
        if _FENCE.match(line):
            in_fence = not in_fence
        elif not in_fence and (m := _HEADING.match(line)):
            text = m.group(2)
            if len(m.group(1)) == 1:
                doc_title = text
                label = text
            else:
                label = f"{doc_title} > {text}" if doc_title else text
            prev = boundaries[-1][0] if boundaries else None
            if prev is not None and all(not lines[k - 1].strip() for k in range(prev + 1, n)):
                # The previous heading has no body of its own: fold it into this section
                # so a title line never becomes a content-free chunk.
                boundaries[-1] = (prev, label)
            else:
                boundaries.append((n, label))
    return _split_at(lines, boundaries, title, body_start)


def chunk_python(rel: str, source: str, lines: list[str]) -> list[RawChunk]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        log.warning("%s: not parseable as Python, using line windows", rel)
        return _split_at(lines, [], rel)
    boundaries = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            start = min([node.lineno, *(d.lineno for d in node.decorator_list)])
            boundaries.append((start, f"{rel}::{node.name}"))
    return _split_at(lines, boundaries, f"{rel} (module header)")


def chunk_sql(rel: str, lines: list[str]) -> list[RawChunk]:
    boundaries = []
    for n, line in enumerate(lines, start=1):
        if _SQL_CREATE.match(line):
            # "CREATE TABLE IF NOT EXISTS loans (" -> "CREATE TABLE IF NOT EXISTS loans"
            boundaries.append((n, f"{rel}::{line.strip().split('(')[0].strip()}"))
    return _split_at(lines, boundaries, f"{rel} (header)")


def load_file(root: Path, path: Path) -> LoadedFile | None:
    """Read and chunk one file. Returns None for files that should be skipped."""
    rel_path = path.relative_to(root)
    rel = rel_path.as_posix()
    data = path.read_bytes()
    if len(data) > MAX_FILE_BYTES:
        log.info("%s: skipped, larger than %d bytes", rel, MAX_FILE_BYTES)
        return None
    try:
        source = data.decode("utf-8")
    except UnicodeDecodeError:
        log.info("%s: skipped, not UTF-8 text", rel)
        return None
    lines = source.splitlines()
    if not any(line.strip() for line in lines):
        return None

    front_matter: dict[str, str] = {}
    suffix = rel_path.suffix.lower()
    if suffix == ".md":
        front_matter, body_start = parse_front_matter(lines)
        chunks = chunk_markdown(rel, lines, body_start + 1, front_matter.get("title", rel))
    elif suffix == ".py":
        chunks = chunk_python(rel, source, lines)
    elif suffix == ".sql":
        chunks = chunk_sql(rel, lines)
    else:
        chunks = _split_at(lines, [], rel)

    windowed = [w for c in chunks for w in _window(c)]
    meta = {k: v for k, v in front_matter.items() if k not in {"kind", "status"}}
    return LoadedFile(
        rel,
        sha256_bytes(data),
        infer_kind(rel_path, front_matter),
        infer_status(rel_path, front_matter),
        windowed,
        meta,
    )
