"""Turn a ContextRequest into a ContextPackage.

Pipeline: extract search terms -> retrieve candidates per requested kind ->
set aside superseded (and, optionally, weak) items -> select within the token
budget, round-robin across kinds so one kind cannot crowd out the others, and
(optionally) right after each selected item the code it names -> check
sources for staleness -> report what could not be found -> emit one
telemetry event.

The orchestrator never invents content: anything it cannot find is reported
under ``unresolved`` instead of being filled in.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import replace
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
    render_header,
    render_item,
    render_unresolved,
)
from context_orchestrator.retrieval.lexical import LexicalRetriever, ScoredChunk, extract_terms
from context_orchestrator.retrieval.references import ReferenceIndex
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
        self.references = ReferenceIndex(store)
        self.telemetry = telemetry or NullTelemetry()
        self.clock = clock

    def handle(self, request: ContextRequest) -> ContextPackage:
        started = self.clock()
        terms = extract_terms(" ".join([request.task, *request.constraints]))
        unresolved: list[str] = []
        unresolved_kinds: list[str] = []
        omitted: list[OmittedItem] = []
        notes: list[str] = []

        if not terms:
            unresolved.append("The task contains no searchable terms; nothing was retrieved.")

        # 1. Retrieve per kind. Over-fetch so superseded items do not use up slots.
        kinds = request.kinds or [None]
        hits_by_kind = [
            self.retriever.search(terms, kind, limit=request.per_kind_limit * 2) for kind in kinds
        ]
        candidates_seen = sum(len(h) for h in hits_by_kind)
        # BM25 scores from one query are comparable across kinds (IDF is index-wide), so a
        # kind whose best hit is far below the query's best hit has nothing really relevant.
        best = max((h.score for hits in hits_by_kind for h in hits), default=0.0)
        threshold = best * request.min_relative_score

        ranked_by_kind: list[list[ScoredChunk]] = []
        for kind, hits in zip(kinds, hits_by_kind, strict=True):
            kept = []
            weak = 0
            for hit in hits:
                if hit.chunk.status is Status.SUPERSEDED and not request.include_superseded:
                    omitted.append(OmittedItem(hit.chunk.source, "superseded"))
                elif hit.score < threshold:
                    weak += 1
                    omitted.append(
                        OmittedItem(
                            hit.chunk.source,
                            f"weak match: score {hit.score:.2f} < {request.min_relative_score:g}"
                            f" x best {best:.2f}",
                        )
                    )
                else:
                    kept.append(hit)
            kept = kept[: request.per_kind_limit]
            if terms and not kept:
                label = kind.value if kind else "project"
                unresolved_kinds.append(kind.value if kind else "any")
                if weak:
                    unresolved.append(
                        f"No relevant {label} information found: only weak matches, far below "
                        "the best match for this task. It may be missing from the knowledge base."
                    )
                else:
                    unresolved.append(
                        f"No {label} information matched the task terms. It may be missing from "
                        "the knowledge base, or described with different vocabulary."
                    )
            ranked_by_kind.append(kept)

        # 2. Select round-robin across kinds within the token budget. The budget covers the
        #    whole rendered package: header and unresolved section are reserved first, and
        #    each item is charged for its rendered block (heading, flags and text).
        items: list[ContextItem] = []
        used_tokens = estimate_tokens(render_header(request.task)) + estimate_tokens(
            render_unresolved(unresolved)
        )
        selected: set[str] = set()
        fingerprints: dict[str, str | None] = {}
        allowed_kinds = set(request.kinds)
        references_added = 0

        def try_add(item: ContextItem, chunk_id: str) -> bool:
            nonlocal used_tokens
            if used_tokens + item.estimated_tokens > request.max_tokens:
                reason = f"token budget: needs ~{item.estimated_tokens}, "
                reason += f"{request.max_tokens - used_tokens} left"
                omitted.append(
                    OmittedItem(item.source, reason + (f" ({item.via})" if item.via else ""))
                )
                return False
            selected.add(chunk_id)
            used_tokens += item.estimated_tokens
            items.append(item)
            return True

        for rank in range(max((len(r) for r in ranked_by_kind), default=0)):
            round_hits = [r[rank] for r in ranked_by_kind if rank < len(r)]
            for hit in sorted(round_hits, key=lambda h: -h.score):
                if hit.chunk.chunk_id in selected:
                    continue
                if not try_add(self._to_item(hit, fingerprints), hit.chunk.chunk_id):
                    continue
                # 3. Follow references from this item right away, so the code a bug report
                #    or ADR names outranks lower-ranked search hits for the budget.
                if references_added >= request.max_references:
                    continue
                for ref in self.references.references_in(hit.chunk):
                    if references_added >= request.max_references:
                        break
                    chunk = ref.chunk
                    if chunk.chunk_id in selected or (
                        allowed_kinds and chunk.kind not in allowed_kinds
                    ):
                        continue
                    via = f"references: `{ref.name}` named in {hit.chunk.source.label()}"
                    ref_item = self._to_item(ScoredChunk(chunk, 0.0, ()), fingerprints, via=via)
                    if try_add(ref_item, chunk.chunk_id):
                        references_added += 1

        # 4. Annotate.
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
        self, hit: ScoredChunk, fingerprints: dict[str, str | None], via: str | None = None
    ) -> ContextItem:
        chunk = hit.chunk
        item = ContextItem(
            kind=chunk.kind,
            status=chunk.status,
            heading=chunk.heading,
            text=chunk.text,
            source=chunk.source,
            score=round(hit.score, 4),
            matched_terms=hit.matched_terms,
            stale=self._is_stale(chunk.source, fingerprints),
            estimated_tokens=0,
            via=via,
        )
        return replace(item, estimated_tokens=estimate_tokens(render_item(item)))

    def _is_stale(self, source: SourceRef, fingerprints: dict[str, str | None]) -> bool | None:
        root = self.store.project_root
        if root is None:
            return None
        if source.path not in fingerprints:
            path = Path(root, source.path)
            fingerprints[source.path] = sha256_bytes(path.read_bytes()) if path.is_file() else None
        return fingerprints[source.path] != source.file_sha256
