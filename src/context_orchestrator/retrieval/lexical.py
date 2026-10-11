"""Explainable keyword retrieval over the memory store (SQLite FTS5 + BM25).

Why keyword search first: it is deterministic, needs no model or extra
dependency, and every result can be explained by the terms it matched. If the
evaluation shows vocabulary mismatch is a real failure mode, a semantic
retriever can be added behind the same ``search`` signature and compared.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from context_orchestrator.memory.store import MemoryStore
from context_orchestrator.models import Chunk, InfoKind, Status

# NLTK's English stopword list (function words only, tokenised the way extract_terms
# splits text, so "don't" contributes "don"). Lists with content words such as "due",
# "bill" or "show" (e.g. scikit-learn's) are avoided: those carry meaning in a codebase.
NLTK_ENGLISH_STOPWORDS = frozenset(
    """i me my myself we our ours ourselves you your yours yourself yourselves he him his
    himself she her hers herself it its itself they them their theirs themselves what which
    who whom this that these those am is are was were be been being have has had having do
    does did doing a an the and but if or because as until while of at by for with about
    against between into through during before after above below to from up down in out on
    off over under again further then once here there when where why how all any both each
    few more most other some such no nor not only own same so than too very can will just
    don should now ll re ve ain aren couldn didn doesn hadn hasn haven isn ma mightn mustn
    needn shan shouldn wasn weren won wouldn""".split()
)

# Words that carry no retrieval signal in task descriptions: function words plus the
# generic verbs and nouns of change requests.
STOPWORDS = NLTK_ENGLISH_STOPWORDS | frozenset(
    """could would please add adding change fix fixing implement implementing make making
    update updating write new use using need needs want task code one also us""".split()
)

_TERM = re.compile(r"[A-Za-z0-9]+")
_MARK_OPEN, _MARK_CLOSE = "\x02", "\x03"
_MARKED = re.compile(f"{_MARK_OPEN}(.*?){_MARK_CLOSE}")


def extract_terms(text: str) -> list[str]:
    """Lower-cased, de-duplicated search terms in order of first appearance."""
    seen: dict[str, None] = {}
    for raw in _TERM.findall(text):
        term = raw.lower()
        if len(term) >= 2 and term not in STOPWORDS and not term.isdigit():
            seen.setdefault(term, None)
    return list(seen)


@dataclass(frozen=True, slots=True)
class ScoredChunk:
    chunk: Chunk
    score: float  # negated BM25: higher is more relevant
    matched_terms: tuple[str, ...]


class LexicalRetriever:
    # BM25 column weights: chunk_id (unindexed), heading, text, path.
    _WEIGHTS = (0.0, 2.0, 1.0, 0.5)

    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def search(
        self,
        terms: list[str],
        kind: InfoKind | None = None,
        limit: int = 5,
        include_superseded: bool = True,
    ) -> list[ScoredChunk]:
        if not terms:
            return []
        match = " OR ".join(f'"{t}"' for t in terms)
        sql = f"""
            SELECT c.*,
                   bm25(chunks_fts, {", ".join(map(str, self._WEIGHTS))}) AS rank,
                   highlight(chunks_fts, 1, ?, ?) AS hl_heading,
                   highlight(chunks_fts, 2, ?, ?) AS hl_text
            FROM chunks_fts JOIN chunks c ON c.chunk_id = chunks_fts.chunk_id
            WHERE chunks_fts MATCH ?
        """
        params: list[object] = [_MARK_OPEN, _MARK_CLOSE, _MARK_OPEN, _MARK_CLOSE, match]
        if kind is not None:
            sql += " AND c.kind = ?"
            params.append(kind.value)
        if not include_superseded:
            sql += " AND c.status != ?"
            params.append(Status.SUPERSEDED.value)
        sql += " ORDER BY rank, c.path, c.line_start LIMIT ?"
        params.append(limit)

        results = []
        for row in self.store.conn.execute(sql, params):
            marked = _MARKED.findall(row["hl_heading"]) + _MARKED.findall(row["hl_text"])
            matched = tuple(dict.fromkeys(m.lower() for m in marked))
            results.append(ScoredChunk(self.store.row_to_chunk(row), -float(row["rank"]), matched))
        return results
