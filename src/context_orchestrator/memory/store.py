"""Persistent project memory backed by a single SQLite file.

The store keeps one row per ingested file (with its hash) and one row per
chunk, plus an FTS5 index used by ``retrieval``. Ingestion is incremental:
unchanged files are skipped by hash, changed files have their chunks replaced,
and files that disappeared are removed. The store only ever reads project
files; it never writes to them.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from context_orchestrator.memory.loader import discover_files, load_file
from context_orchestrator.models import Chunk, InfoKind, SourceRef, Status

log = logging.getLogger(__name__)

SCHEMA_VERSION = "1"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
    path        TEXT PRIMARY KEY,
    sha256      TEXT NOT NULL,
    kind        TEXT NOT NULL,
    status      TEXT NOT NULL,
    ingested_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id      TEXT PRIMARY KEY,
    path          TEXT NOT NULL REFERENCES documents(path) ON DELETE CASCADE,
    kind          TEXT NOT NULL,
    status        TEXT NOT NULL,
    heading       TEXT NOT NULL,
    text          TEXT NOT NULL,
    line_start    INTEGER NOT NULL,
    line_end      INTEGER NOT NULL,
    metadata_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS chunks_path ON chunks(path);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    chunk_id UNINDEXED, heading, text, path,
    tokenize = 'porter unicode61'
);
"""


@dataclass(slots=True)
class IngestReport:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    chunks_written: int = 0


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class MemoryStore:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(_SCHEMA)
        self.conn.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)", (SCHEMA_VERSION,)
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> MemoryStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- metadata ---------------------------------------------------------

    @property
    def project_root(self) -> Path | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key = 'project_root'").fetchone()
        return Path(row["value"]) if row else None

    def _set_project_root(self, root: Path) -> None:
        current = self.project_root
        if current is not None and current != root:
            raise ValueError(
                f"Store {self.db_path} belongs to project {current}, not {root}. "
                "Use a separate state directory per project."
            )
        self.conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES ('project_root', ?)", (str(root),)
        )

    # -- ingestion --------------------------------------------------------

    def ingest(self, project_root: Path | str) -> IngestReport:
        root = Path(project_root).resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"Project root does not exist: {root}")
        report = IngestReport()
        known = {
            r["path"]: r["sha256"] for r in self.conn.execute("SELECT path, sha256 FROM documents")
        }
        seen: set[str] = set()

        with self.conn:  # one transaction for the whole ingest
            self._set_project_root(root)
            for path in discover_files(root):
                rel = path.relative_to(root).as_posix()
                loaded = load_file(root, path)
                if loaded is None:
                    report.skipped.append(rel)
                    continue
                seen.add(rel)
                if known.get(rel) == loaded.sha256:
                    report.unchanged.append(rel)
                    continue
                (report.updated if rel in known else report.added).append(rel)
                self._delete_document(rel)
                ingested_at = _now()
                self.conn.execute(
                    "INSERT INTO documents(path, sha256, kind, status, ingested_at) "
                    "VALUES (?,?,?,?,?)",
                    (rel, loaded.sha256, loaded.kind.value, loaded.status.value, ingested_at),
                )
                for raw in loaded.chunks:
                    chunk_id = hashlib.sha256(
                        f"{rel}:{raw.line_start}:{raw.line_end}:{loaded.sha256}".encode()
                    ).hexdigest()[:16]
                    self.conn.execute(
                        "INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?)",
                        (
                            chunk_id,
                            rel,
                            loaded.kind.value,
                            loaded.status.value,
                            raw.heading,
                            raw.text,
                            raw.line_start,
                            raw.line_end,
                            json.dumps(loaded.metadata),
                        ),
                    )
                    self.conn.execute(
                        "INSERT INTO chunks_fts(chunk_id, heading, text, path) VALUES (?,?,?,?)",
                        (chunk_id, raw.heading, raw.text, rel),
                    )
                    report.chunks_written += 1
            for rel in sorted(set(known) - seen):
                self._delete_document(rel)
                report.removed.append(rel)

        log.info(
            "ingest %s: %d added, %d updated, %d unchanged, %d removed, %d skipped",
            root,
            len(report.added),
            len(report.updated),
            len(report.unchanged),
            len(report.removed),
            len(report.skipped),
        )
        return report

    def _delete_document(self, rel: str) -> None:
        self.conn.execute(
            "DELETE FROM chunks_fts WHERE chunk_id IN (SELECT chunk_id FROM chunks WHERE path = ?)",
            (rel,),
        )
        self.conn.execute("DELETE FROM documents WHERE path = ?", (rel,))  # cascades to chunks

    # -- reads ------------------------------------------------------------

    def row_to_chunk(self, row: sqlite3.Row) -> Chunk:
        doc = self.conn.execute(
            "SELECT sha256, ingested_at FROM documents WHERE path = ?", (row["path"],)
        ).fetchone()
        return Chunk(
            chunk_id=row["chunk_id"],
            kind=InfoKind(row["kind"]),
            status=Status(row["status"]),
            heading=row["heading"],
            text=row["text"],
            source=SourceRef(
                row["path"], row["line_start"], row["line_end"], doc["sha256"], doc["ingested_at"]
            ),
            metadata=json.loads(row["metadata_json"]),
        )

    def chunk_by_source(self, source: SourceRef) -> Chunk | None:
        row = self.conn.execute(
            "SELECT * FROM chunks WHERE path = ? AND line_start = ? AND line_end = ?",
            (source.path, source.line_start, source.line_end),
        ).fetchone()
        return self.row_to_chunk(row) if row else None

    def iter_chunks(self) -> Iterator[Chunk]:
        for row in self.conn.execute("SELECT * FROM chunks ORDER BY path, line_start"):
            yield self.row_to_chunk(row)

    def count_chunks(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
