"""The entry point agents (or adapters such as a future MCP server) call.

State for a project lives in one directory, ``<project>/.ctxo`` by default:
``memory.db`` (SQLite) and ``telemetry.jsonl``. Nothing else in the project
is written to.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from context_orchestrator.memory.loader import sha256_bytes
from context_orchestrator.memory.store import IngestReport, MemoryStore
from context_orchestrator.models import ContextPackage, ContextRequest, Finding, SourceRef
from context_orchestrator.orchestrator.service import ContextOrchestrator
from context_orchestrator.telemetry.events import JsonlTelemetry, NullTelemetry, TelemetrySink

STATE_DIR_NAME = ".ctxo"
DB_NAME = "memory.db"
TELEMETRY_NAME = "telemetry.jsonl"
RETRIEVAL_MODES = ("bm25", "hybrid", "semantic")
MIN_CLAIM_CHARS, MAX_CLAIM_CHARS = 20, 800
MAX_EVIDENCE_CHARS = 400
MAX_FINDING_LINES = 60


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


class Embedder(Protocol):
    model: str

    def embed(self, texts: Sequence[str], purpose: str) -> list[list[float]]: ...


class ContextService:
    def __init__(
        self,
        project_root: Path | str,
        state_dir: Path | str | None = None,
        telemetry: TelemetrySink | None = None,
        record_task_text: bool = False,
        retrieval: str = "bm25",
        embedder: Embedder | None = None,
    ) -> None:
        """``retrieval``: "bm25" (keyword only, no dependencies), "hybrid" (BM25 plus
        embeddings) or "semantic" (embeddings only). The latter two need ``embedder``
        (by default a local Ollama server, see ``retrieval.semantic``)."""
        if retrieval not in RETRIEVAL_MODES:
            raise ValueError(f"retrieval must be one of {RETRIEVAL_MODES}, not {retrieval!r}")
        self.retrieval = retrieval
        self.embedder = embedder
        if retrieval != "bm25" and embedder is None:
            from context_orchestrator.retrieval.semantic import OllamaEmbedder

            self.embedder = OllamaEmbedder()
        self._retriever_stale = retrieval != "bm25"
        self.project_root = Path(project_root).resolve()
        self.state_dir = Path(state_dir) if state_dir else self.project_root / STATE_DIR_NAME
        self.store = MemoryStore(self.state_dir / DB_NAME)
        if telemetry is None:
            telemetry = JsonlTelemetry(self.state_dir / TELEMETRY_NAME, record_task_text)
        self.orchestrator = ContextOrchestrator(self.store, telemetry=telemetry)

    @classmethod
    def without_telemetry(
        cls, project_root: Path | str, state_dir: Path | str | None = None
    ) -> ContextService:
        return cls(project_root, state_dir, telemetry=NullTelemetry())

    def ingest(self) -> IngestReport:
        report = self.store.ingest(self.project_root)
        if self.embedder is not None:
            from context_orchestrator.retrieval.semantic import embed_missing

            report.chunks_embedded = embed_missing(self.store, self.embedder)
            self._retriever_stale = True
        return report

    def _ensure_retriever(self) -> None:
        if self._retriever_stale and self.embedder is not None:
            from context_orchestrator.retrieval.semantic import HybridRetriever

            self.orchestrator.retriever = HybridRetriever(
                self.store, self.embedder, mode=self.retrieval
            )
            self._retriever_stale = False

    def request(self, request: ContextRequest | dict[str, Any]) -> ContextPackage:
        if isinstance(request, dict):
            request = ContextRequest.from_dict(request)
        if self.store.count_chunks() == 0:
            raise RuntimeError("The knowledge base is empty. Run ingest first.")
        self._ensure_retriever()
        return self.orchestrator.handle(request)

    def record_finding(
        self,
        claim: str,
        path: str,
        line_start: int,
        line_end: int,
        evidence: str,
        agent_id: str = "anonymous",
    ) -> Finding:
        """Store something an agent worked out, after checking its anchor.

        The cited lines must exist and contain ``evidence`` verbatim (whitespace
        is normalised), so a finding cannot point at lines that do not say it.
        The finding is stored unreviewed in the state directory; the project's
        files are never written. Raises ValueError with a readable reason.
        """
        claim, evidence = claim.strip(), evidence.strip()
        if not MIN_CLAIM_CHARS <= len(claim) <= MAX_CLAIM_CHARS:
            raise ValueError(f"claim must be {MIN_CLAIM_CHARS}-{MAX_CLAIM_CHARS} characters")
        if not evidence or len(evidence) > MAX_EVIDENCE_CHARS:
            raise ValueError(f"evidence must be 1-{MAX_EVIDENCE_CHARS} characters")
        rel = path.replace("\\", "/").removeprefix("./")
        file = (self.project_root / rel).resolve()
        rel = (
            file.relative_to(self.project_root).as_posix()
            if file.is_relative_to(self.project_root)
            else rel
        )
        if not file.is_relative_to(self.project_root) or not file.is_file():
            raise ValueError(f"no such file in the project: {path}")
        data = file.read_bytes()
        lines = data.decode("utf-8", "replace").splitlines()
        if not 1 <= line_start <= line_end <= len(lines):
            raise ValueError(f"{rel} has {len(lines)} lines; cited {line_start}-{line_end}")
        if line_end - line_start + 1 > MAX_FINDING_LINES:
            raise ValueError(f"cite at most {MAX_FINDING_LINES} lines")
        cited = _squash("\n".join(lines[line_start - 1 : line_end]))
        if _squash(evidence) not in cited:
            raise ValueError(f"evidence is not a verbatim quote from {rel}:{line_start}-{line_end}")
        recorded_at = datetime.now(UTC).isoformat(timespec="seconds")
        finding = Finding(
            finding_id=hashlib.sha256(
                f"{rel}:{line_start}:{line_end}:{claim}:{recorded_at}".encode()
            ).hexdigest()[:16],
            claim=claim,
            evidence=evidence,
            source=SourceRef(rel, line_start, line_end, sha256_bytes(data), recorded_at),
            agent_id=agent_id,
        )
        self.store.add_finding(finding)
        return finding

    def close(self) -> None:
        self.store.close()

    def __enter__(self) -> ContextService:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
