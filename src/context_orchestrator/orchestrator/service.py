"""Turn a ContextRequest into a ContextPackage.

Pipeline: extract search terms -> retrieve candidates per requested kind ->
set aside superseded items -> select within the token budget (round-robin
across kinds so one kind cannot crowd out the others) -> check sources for
staleness -> report what could not be found -> emit one telemetry event.

The orchestrator never invents content: anything it cannot find is reported
under ``unresolved`` instead of being filled in.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path

from context_orchestrator.memory.loader import sha256_bytes
from context_orchestrator.memory.store import MemoryStore
from context_orchestrator.models import (
    ContextItem,
    ContextPackage,
    ContextRequest,
    Metric,
    OmittedItem,
    SourceRef,
    Status,
)
from context_orchestrator.retrieval.lexical import LexicalRetriever, ScoredChunk, extract_terms
from context_orchestrator.telemetry.events import (
    NullTelemetry,
    TelemetrySink,
    context_request_event,
)
from context_orchestrator.tokens import ESTIMATE_METHOD, estimate_tokens

log = logging.getLogger(__name__)


class ContextOrchestrator:
    def __init__(
        self,
        store: MemoryStore,
        retriever: LexicalRetriever | None = None,
        telemetry: TelemetrySink | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.store = store
        self.retriever = retriever or LexicalRetriever(store)
        self.telemetry = telemetry or NullTelemetry()
        self.clock = clock

    def handle(self, request: ContextRequest) -> ContextPackage:
        started = self.clock()
        terms = extract_terms(" ".join([request.task, *request.constraints]))
        unresolved: list[str] = []
        unresolved_kinds: list[str] = []
        omitted: list[OmittedItem] = []
        notes: list[str] = []
        candidates_seen = 0

        if not terms:
            unresolved.append("The task contains no searchable terms; nothing was retrieved.")

        # 1. Retrieve per kind. Over-fetch so superseded items do not use up slots.
        ranked_by_kind: list[list[ScoredChunk]] = []
        for kind in request.kinds or [None]:
            hits = self.retriever.search(terms, kind, limit=request.per_kind_limit * 2)
            candidates_seen += len(hits)
            kept = []
            for hit in hits:
                if hit.chunk.status is Status.SUPERSEDED and not request.include_superseded:
                    omitted.append(OmittedItem(hit.chunk.source, "superseded"))
                else:
                    kept.append(hit)
            kept = kept[: request.per_kind_limit]
            if terms and not kept:
                label = kind.value if kind else "project"
                unresolved_kinds.append(kind.value if kind else "any")
                unresolved.append(
                    f"No {label} information matched the task terms. It may be missing from the "
                    "knowledge base, or described with different vocabulary."
                )
            ranked_by_kind.append(kept)

        # 2. Select round-robin across kinds within the token budget.
        items: list[ContextItem] = []
        used_tokens = 0
        selected: set[str] = set()
        fingerprints: dict[str, str | None] = {}
        for rank in range(max((len(r) for r in ranked_by_kind), default=0)):
            round_hits = [r[rank] for r in ranked_by_kind if rank < len(r)]
            for hit in sorted(round_hits, key=lambda h: -h.score):
                if hit.chunk.chunk_id in selected:
                    continue
                cost = estimate_tokens(hit.chunk.text)
                if used_tokens + cost > request.max_tokens:
                    omitted.append(
                        OmittedItem(
                            hit.chunk.source,
                            f"token budget: needs ~{cost}, {request.max_tokens - used_tokens} left",
                        )
                    )
                    continue
                selected.add(hit.chunk.chunk_id)
                used_tokens += cost
                items.append(self._to_item(hit, cost, fingerprints))

        # 3. Annotate.
        stale = [i for i in items if i.stale]
        if stale:
            notes.append(
                f"{len(stale)} item(s) come from files that changed since ingestion; "
                "re-run ingest before relying on them."
            )
        for item in items:
            if item.status is Status.ASSUMPTION:
                notes.append(f"{item.source.label()} is recorded as an assumption, not verified.")

        package = ContextPackage(
            request_id=request.request_id,
            task=request.task,
            items=items,
            unresolved=unresolved,
            omitted=omitted,
            estimated_tokens=Metric.estimated(0, ESTIMATE_METHOD),
            query_terms=terms,
            notes=notes,
            unresolved_kinds=unresolved_kinds,
        )
        package.estimated_tokens = Metric.estimated(
            estimate_tokens(package.render_markdown()), ESTIMATE_METHOD
        )
        latency_ms = (self.clock() - started) * 1000
        self.telemetry.emit(context_request_event(request, package, latency_ms, candidates_seen))
        log.debug(
            "request %s: %d items, %d unresolved", request.request_id, len(items), len(unresolved)
        )
        return package

    # -- helpers ------------------------------------------------------------

    def _to_item(
        self, hit: ScoredChunk, cost: int, fingerprints: dict[str, str | None]
    ) -> ContextItem:
        chunk = hit.chunk
        return ContextItem(
            kind=chunk.kind,
            status=chunk.status,
            heading=chunk.heading,
            text=chunk.text,
            source=chunk.source,
            score=round(hit.score, 4),
            matched_terms=hit.matched_terms,
            stale=self._is_stale(chunk.source, fingerprints),
            estimated_tokens=cost,
        )

    def _is_stale(self, source: SourceRef, fingerprints: dict[str, str | None]) -> bool | None:
        root = self.store.project_root
        if root is None:
            return None
        if source.path not in fingerprints:
            path = Path(root, source.path)
            fingerprints[source.path] = sha256_bytes(path.read_bytes()) if path.is_file() else None
        return fingerprints[source.path] != source.file_sha256
