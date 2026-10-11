"""The entry point agents (or adapters such as a future MCP server) call.

State for a project lives in one directory, ``<project>/.ctxo`` by default:
``memory.db`` (SQLite) and ``telemetry.jsonl``. Nothing else in the project
is written to.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from context_orchestrator.memory.store import IngestReport, MemoryStore
from context_orchestrator.models import ContextPackage, ContextRequest
from context_orchestrator.orchestrator.service import ContextOrchestrator
from context_orchestrator.telemetry.events import JsonlTelemetry, NullTelemetry, TelemetrySink

STATE_DIR_NAME = ".ctxo"
DB_NAME = "memory.db"
TELEMETRY_NAME = "telemetry.jsonl"
RETRIEVAL_MODES = ("bm25", "hybrid", "semantic")


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

    def close(self) -> None:
        self.store.close()

    def __enter__(self) -> ContextService:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
