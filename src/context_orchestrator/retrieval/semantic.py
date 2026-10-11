"""Optional meaning-based retrieval: embeddings plus BM25 fused by rank.

Embeddings come from a local Ollama server over HTTP (standard library only),
so the core keeps no third-party dependencies and nothing leaves the machine.
Vectors live in the memory store, one per chunk and model.

Hybrid ranking uses reciprocal rank fusion (RRF): each chunk scores
``sum(1 / (k + rank))`` over the BM25 list and the vector list. RRF needs no
score calibration between the two very different scales, which is why it is
the usual first choice for combining them.
"""

from __future__ import annotations

import json
import logging
import math
import urllib.error
import urllib.request
from array import array
from collections.abc import Sequence
from dataclasses import dataclass, field

from context_orchestrator.memory.store import MemoryStore
from context_orchestrator.models import InfoKind
from context_orchestrator.retrieval.lexical import LexicalRetriever, ScoredChunk

log = logging.getLogger(__name__)

DEFAULT_MODEL = "nomic-embed-text"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
RRF_K = 60
CANDIDATES_PER_LIST = 50
MAX_EMBED_CHARS = 8000  # keeps long chunks inside the model's context window

# nomic-embed-text is trained with task prefixes; other models get none.
_PREFIXES = {"nomic-embed-text": ("search_query: ", "search_document: ")}


class EmbeddingError(RuntimeError):
    pass


@dataclass(slots=True)
class OllamaEmbedder:
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_OLLAMA_URL
    timeout: float = 120.0
    batch_size: int = 32
    _digest: str | None = field(default=None, init=False)

    def _post(self, path: str, payload: dict) -> dict:
        request = urllib.request.Request(
            self.base_url.rstrip("/") + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise EmbeddingError(
                f"Ollama at {self.base_url} did not answer ({exc}). Is `ollama serve` running "
                f"and is `{self.model}` pulled?"
            ) from exc

    def _prefix(self, purpose: str) -> str:
        query, document = _PREFIXES.get(self.model.split(":")[0], ("", ""))
        return query if purpose == "query" else document

    def embed(self, texts: Sequence[str], purpose: str) -> list[list[float]]:
        prefix = self._prefix(purpose)
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = [prefix + t[:MAX_EMBED_CHARS] for t in texts[start : start + self.batch_size]]
            data = self._post(
                "/api/embed",
                {"model": self.model, "input": batch, "truncate": True,
                 "options": {"num_ctx": 8192}},
            )  # fmt: skip
            vectors.extend(data["embeddings"])
        return vectors

    def model_id(self) -> str:
        """Model name plus the digest Ollama reports, for reproducibility records."""
        if self._digest is None:
            try:
                data = self._post("/api/show", {"model": self.model})
                self._digest = str(data.get("digest") or data.get("details", {}).get("digest", ""))
            except EmbeddingError:
                self._digest = ""
            if not self._digest:
                request = urllib.request.Request(self.base_url.rstrip("/") + "/api/tags")
                try:
                    with urllib.request.urlopen(request, timeout=self.timeout) as response:
                        tags = json.loads(response.read())
                    for m in tags.get("models", []):
                        if m.get("name", "").split(":")[0] == self.model.split(":")[0]:
                            self._digest = m.get("digest", "")
                except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
                    pass
        return f"{self.model}@{(self._digest or 'unknown')[:12]}"


def _pack(vector: Sequence[float]) -> bytes:
    return array("f", vector).tobytes()


def _unpack(blob: bytes) -> array:
    values = array("f")
    values.frombytes(blob)
    return values


def _norm(values: Sequence[float]) -> float:
    return math.sqrt(sum(v * v for v in values)) or 1.0


def embed_missing(store: MemoryStore, embedder: OllamaEmbedder) -> int:
    """Embed every chunk that has no vector for this model yet. Returns how many."""
    rows = store.conn.execute(
        "SELECT c.chunk_id, c.heading, c.text FROM chunks c LEFT JOIN chunk_vectors v "
        "ON v.chunk_id = c.chunk_id AND v.model = ? WHERE v.chunk_id IS NULL",
        (embedder.model,),
    ).fetchall()
    if not rows:
        return 0
    vectors = embedder.embed([f"{r['heading']}\n{r['text']}" for r in rows], "document")
    with store.conn:
        store.conn.executemany(
            "INSERT OR REPLACE INTO chunk_vectors(chunk_id, model, dim, vector) VALUES (?,?,?,?)",
            [
                (r["chunk_id"], embedder.model, len(v), _pack(v))
                for r, v in zip(rows, vectors, strict=True)
            ],
        )
    log.info("embedded %d chunks with %s", len(rows), embedder.model)
    return len(rows)


class VectorIndex:
    """All of one model's chunk vectors, held in memory for brute-force cosine search."""

    def __init__(self, store: MemoryStore, model: str) -> None:
        self.entries: list[tuple[str, str, array, float]] = []  # chunk_id, kind, vector, norm
        rows = store.conn.execute(
            "SELECT v.chunk_id, c.kind, v.vector FROM chunk_vectors v "
            "JOIN chunks c ON c.chunk_id = v.chunk_id WHERE v.model = ?",
            (model,),
        )
        for row in rows:
            vector = _unpack(row["vector"])
            self.entries.append((row["chunk_id"], row["kind"], vector, _norm(vector)))

    def similarities(self, query: Sequence[float]) -> dict[str, tuple[str, float]]:
        """chunk_id -> (kind, cosine similarity) for every indexed chunk."""
        q_norm = _norm(query)
        return {
            chunk_id: (
                kind,
                sum(a * b for a, b in zip(query, vector, strict=True)) / (q_norm * norm),
            )
            for chunk_id, kind, vector, norm in self.entries
        }


class HybridRetriever(LexicalRetriever):
    """BM25 and vector similarity fused per kind; ``mode="semantic"`` uses vectors only."""

    def __init__(self, store: MemoryStore, embedder: OllamaEmbedder, mode: str = "hybrid") -> None:
        super().__init__(store)
        if mode not in {"hybrid", "semantic"}:
            raise ValueError(f"unknown retrieval mode {mode!r}")
        self.embedder = embedder
        self.mode = mode
        self.index = VectorIndex(store, embedder.model)
        self._cache: dict[str, dict[str, tuple[str, float]]] = {}

    def similarities_for(self, query_text: str) -> dict[str, tuple[str, float]]:
        if query_text not in self._cache:
            query = self.embedder.embed([query_text], "query")[0]
            self._cache = {query_text: self.index.similarities(query)}  # keep only the latest
        return self._cache[query_text]

    def search(
        self,
        terms: list[str],
        kind: InfoKind | None = None,
        limit: int = 5,
        include_superseded: bool = True,
        query_text: str | None = None,
    ) -> list[ScoredChunk]:
        if not query_text:
            return super().search(terms, kind, limit, include_superseded)
        sims = self.similarities_for(query_text)
        vector_ranked = sorted(
            ((cid, s) for cid, (k, s) in sims.items() if kind is None or k == kind.value),
            key=lambda x: -x[1],
        )[:CANDIDATES_PER_LIST]
        lexical = (
            super().search(terms, kind, CANDIDATES_PER_LIST, include_superseded)
            if self.mode == "hybrid"
            else []
        )
        fused: dict[str, float] = {}
        for rank, hit in enumerate(lexical, 1):
            fused[hit.chunk.chunk_id] = fused.get(hit.chunk.chunk_id, 0.0) + 1 / (RRF_K + rank)
        for rank, (cid, _) in enumerate(vector_ranked, 1):
            fused[cid] = fused.get(cid, 0.0) + 1 / (RRF_K + rank)
        by_id = {hit.chunk.chunk_id: hit for hit in lexical}

        results: list[ScoredChunk] = []
        for cid, score in sorted(fused.items(), key=lambda x: -x[1]):
            hit = by_id.get(cid)
            chunk = hit.chunk if hit else self._chunk(cid)
            if not include_superseded and chunk.status.value == "superseded":
                continue
            results.append(
                ScoredChunk(
                    chunk,
                    score * 1000,  # RRF scores are tiny; scaled only for readability
                    hit.matched_terms if hit else (),
                    similarity=round(sims[cid][1], 4) if cid in sims else None,
                )
            )
            if len(results) >= limit:
                break
        return results

    def _chunk(self, chunk_id: str):
        row = self.store.conn.execute(
            "SELECT * FROM chunks WHERE chunk_id = ?", (chunk_id,)
        ).fetchone()
        return self.store.row_to_chunk(row)
