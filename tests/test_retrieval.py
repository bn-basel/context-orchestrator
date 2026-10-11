from context_orchestrator.agent_interface.api import ContextService
from context_orchestrator.models import InfoKind
from context_orchestrator.retrieval.lexical import LexicalRetriever, extract_terms


def test_extract_terms_drops_stopwords_and_duplicates() -> None:
    assert extract_terms("Fix the fine cap; the FINE must use cents (ADR 0004)") == [
        "fine",
        "cap",
        "must",
        "cents",
        "adr",
    ]


def test_extract_terms_on_empty_text() -> None:
    assert extract_terms("please fix this") == []


def test_search_finds_the_relevant_schema(service: ContextService) -> None:
    hits = LexicalRetriever(service.store).search(["loans", "returned"], InfoKind.SCHEMA, limit=3)
    assert all(h.chunk.kind is InfoKind.SCHEMA for h in hits)
    # Known BM25 behaviour (see README limitations): the one-line index on loans outranks
    # the longer table definition, because shorter chunks score higher.
    assert {h.chunk.heading for h in hits[:2]} == {
        "db/schema.sql::CREATE TABLE loans",
        "db/schema.sql::CREATE INDEX loans_member_active ON loans",
    }
    table = next(h for h in hits if h.chunk.heading.endswith("CREATE TABLE loans"))
    assert "returned_at" not in table.matched_terms  # tokens, not substrings
    assert {"loans", "returned"} <= set(table.matched_terms)


def test_search_stems_terms(service: ContextService) -> None:
    # "renewing" (query) matches "renew"/"renewals" (text) via the Porter stemmer.
    hits = LexicalRetriever(service.store).search(["renewing"], InfoKind.CODE, limit=1)
    assert hits[0].chunk.heading == "src/shelfwise/loans.py::renew"


def test_scores_are_ordered(service: ContextService) -> None:
    hits = LexicalRetriever(service.store).search(["fine", "cents"], None, limit=10)
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)


def test_superseded_can_be_excluded(service: ContextService) -> None:
    retriever = LexicalRetriever(service.store)
    with_old = retriever.search(["float", "dollars"], InfoKind.DECISION, limit=5)
    without_old = retriever.search(
        ["float", "dollars"], InfoKind.DECISION, limit=5, include_superseded=False
    )
    assert any("0002" in h.chunk.source.path for h in with_old)
    assert not any("0002" in h.chunk.source.path for h in without_old)
