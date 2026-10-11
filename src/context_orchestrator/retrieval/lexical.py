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

# Words that carry no retrieval signal in task descriptions.
STOPWORDS = frozenset(
    """a an and are as at be been but by can could do does for from has have how i if in into
    is it its me my of on or our please should so that the their them then there these this
    those to us was we were what when where which while who why will with would you your
    add adding change fix fixing implement implementing make making update updating write
    new use using need needs want task code
    not no one all any some also just only than very more most other such same each both""".split()
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
