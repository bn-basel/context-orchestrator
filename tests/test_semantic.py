"""Semantic retrieval tests with a deterministic fake embedder (no Ollama needed)."""

import hashlib
import json
import re
from pathlib import Path

import pytest

from context_orchestrator.agent_interface.api import ContextService
from context_orchestrator.evaluation.retrieval_eval import RetrievalConfig, load_suite, run_suite
from context_orchestrator.models import ContextRequest, InfoKind
from context_orchestrator.retrieval.semantic import (
    EmbeddingError,
    HybridRetriever,
    OllamaEmbedder,
    VectorIndex,
    embed_missing,
)

COMMITTED_SUITE = (
    Path(__file__).resolve().parents[1] / "benchmarks" / "tasks" / "sample_project.json"
)

# Words that mean the same thing share a dimension, so "penalty" lands near "fine".
SYNONYMS = {"penalty": "fine", "fines": "fine", "patrons": "members", "deadline": "due"}


class FakeEmbedder:
    model = "fake-embed"

    def __init__(self) -> None:
        self.calls = 0
        self.texts_embedded = 0

    def embed(self, texts, purpose):
        self.calls += 1
        self.texts_embedded += len(texts)
        out = []
        for text in texts:
            vec = [0.0] * 64
            for word in re.findall(r"[a-z]+", text.lower()):
                word = SYNONYMS.get(word, word)
                vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % 64] += 1.0
            out.append(vec)
        return out


def test_embed_missing_is_incremental_and_cascades(project: Path, tmp_path: Path) -> None:
    fake = FakeEmbedder()
    with ContextService.without_telemetry(project, tmp_path / "s") as svc:
        svc.embedder = fake
        svc.ingest()
        total = svc.store.count_chunks()
        assert fake.texts_embedded == total
        svc.ingest()  # nothing changed
        assert fake.texts_embedded == total
        notes = project / "docs" / "conventions.md"
        notes.write_text(
            notes.read_text(encoding="utf-8") + "\n## Extra\nMore.\n", encoding="utf-8"
        )
        svc.ingest()
        assert 0 < fake.texts_embedded - total < 10  # only the changed file
        vectors = svc.store.conn.execute("SELECT COUNT(*) FROM chunk_vectors").fetchone()[0]
        assert vectors == svc.store.count_chunks()  # old vectors removed with their chunks


def test_vector_index_ranks_by_cosine(project: Path, tmp_path: Path) -> None:
    fake = FakeEmbedder()
    with ContextService.without_telemetry(project, tmp_path / "s") as svc:
        svc.ingest()
        embed_missing(svc.store, fake)
        index = VectorIndex(svc.store, fake.model)
        sims = index.similarities(fake.embed(["renew loan due date"], "query")[0])
        assert len(sims) == svc.store.count_chunks()
        assert all(-1.0001 <= s <= 1.0001 for _, s in sims.values())


def test_hybrid_finds_synonyms_that_bm25_misses(project: Path, tmp_path: Path) -> None:
    task = "waive the penalty for patrons after the deadline"
    request = dict(task=task, kinds=[InfoKind.CONSTRAINT])
    with ContextService(project, tmp_path / "a", retrieval="bm25") as bm25:
        bm25.ingest()
        lexical = bm25.request(ContextRequest(**request))
    with ContextService(project, tmp_path / "b", retrieval="hybrid", embedder=FakeEmbedder()) as hy:
        hy.ingest()
        hybrid = hy.request(ContextRequest(**request))
    fine_rate = "docs/constraints.md"
    assert fine_rate not in {i.source.path for i in lexical.items}  # no shared words
    assert fine_rate in {i.source.path for i in hybrid.items}  # found through "penalty" ~ "fine"
    assert all(i.similarity is not None for i in hybrid.items)
    assert all(i.similarity is None for i in lexical.items)
    # Items found only by vectors carry a similarity but no matched terms.
    assert any(not i.matched_terms for i in hybrid.items)


def test_semantic_mode_uses_vectors_only(project: Path, tmp_path: Path) -> None:
    with ContextService(
        project, tmp_path / "s", retrieval="semantic", embedder=FakeEmbedder()
    ) as s:
        s.ingest()
        package = s.request(ContextRequest(task="fine cap replacement cost"))
        retriever = s.orchestrator.retriever
    assert isinstance(retriever, HybridRetriever) and retriever.mode == "semantic"
    assert package.items and all(not i.matched_terms for i in package.items)


def test_invalid_mode_and_unreachable_server(project: Path, tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        ContextService(project, tmp_path / "x", retrieval="magic")
    embedder = OllamaEmbedder(base_url="http://127.0.0.1:9", timeout=0.5)
    with pytest.raises(EmbeddingError, match="did not answer"):
        embedder.embed(["hello"], "query")
    assert embedder.model_id().startswith("nomic-embed-text@")


def test_run_suite_records_the_embedding_model(tmp_path: Path) -> None:
    run = run_suite(
        load_suite(COMMITTED_SUITE),
        tmp_path,
        RetrievalConfig(retrieval="hybrid", embed_model="fake-embed"),
        embedder=FakeEmbedder(),
    )
    meta = json.loads((run.run_dir / "run.json").read_text(encoding="utf-8"))
    assert meta["embedding_model"] == "fake-embed"
    assert meta["config"]["retrieval"] == "hybrid"
    assert "retrieval=hybrid (fake-embed)" in (run.run_dir / "summary.md").read_text(
        encoding="utf-8"
    )
