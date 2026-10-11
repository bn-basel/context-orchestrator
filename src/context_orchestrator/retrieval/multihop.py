"""Two-step retrieval: search, then search again for what the best results name.

An engineer reading a bug report goes on to the function it mentions, then to
that function's tests and the helpers it calls. A single query cannot make
those hops, because the later pieces share neither words nor topic with the
task. This module makes one such hop without any model:

1. Take the top results of the first search (the *seeds*).
2. Collect the names they mention or define: functions and classes that exist
   in the codebase (and are not defined in many places), and schema tables
   whose names are specific (contain an underscore).
3. Search again with those names as phrases (``occurrence_windows`` is indexed
   as the tokens "occurrence windows").
4. Fuse the first and second rankings with reciprocal rank fusion, for code,
   test and schema kinds only: the names are code identifiers, so documents,
   decisions and known issues keep the ranking the task itself produced.

Measured limitation: the follow-up is only as good as the seeds. On Hallpass
only about half of the top-4 first-search results are relevant, so half the
names come from the wrong chunks ("query drift") and recall does not improve.
"""

from __future__ import annotations

from context_orchestrator.models import Chunk, InfoKind
from context_orchestrator.retrieval.lexical import ScoredChunk
from context_orchestrator.retrieval.references import ReferenceIndex, mentioned_names

SEED_COUNT = 4
FOLLOW_UP_KINDS = frozenset({InfoKind.CODE, InfoKind.TEST, InfoKind.SCHEMA})
CANDIDATES = 50  # depth of each ranking that gets fused
MAX_NAMES = 12
MAX_DEFINITIONS_PER_NAME = 3
MIN_NAME_LENGTH = 5
RRF_K = 60


def expansion_names(seeds: list[Chunk], references: ReferenceIndex) -> list[str]:
    tables = {t for t in references.table_names() if "_" in t}
    names: list[str] = []
    for seed in seeds:
        for name in mentioned_names(seed.text):
            if name in names or len(name) < MIN_NAME_LENGTH:
                continue
            defined = references.definition_count(name)
            if 0 < defined <= MAX_DEFINITIONS_PER_NAME or name.lower() in tables:
                names.append(name)
    return names[:MAX_NAMES]


def as_phrase(name: str) -> str:
    """How FTS tokenises an identifier: snake_case parts as one phrase."""
    return " ".join(part for part in name.lower().split("_") if part)


def fuse(
    first: list[ScoredChunk], second: list[ScoredChunk], names: list[str]
) -> list[ScoredChunk]:
    """Reciprocal rank fusion of two rankings; hits only the follow-up found get a ``via``."""
    scores: dict[str, float] = {}
    best: dict[str, ScoredChunk] = {}
    for ranking in (first, second):
        for rank, hit in enumerate(ranking, 1):
            cid = hit.chunk.chunk_id
            scores[cid] = scores.get(cid, 0.0) + 1 / (RRF_K + rank)
            best.setdefault(cid, hit)
    first_ids = {h.chunk.chunk_id for h in first}
    second_terms = {h.chunk.chunk_id: h.matched_terms for h in second}
    via = "follow-up search for names in the top results: " + ", ".join(f"`{n}`" for n in names[:4])
    fused = []
    for cid, score in sorted(scores.items(), key=lambda x: -x[1]):
        hit = best[cid]
        terms = tuple(dict.fromkeys(hit.matched_terms + second_terms.get(cid, ())))
        fused.append(
            ScoredChunk(
                hit.chunk,
                score * 1000,  # RRF scores are tiny; scaled only for readability
                terms,
                similarity=hit.similarity,
                via=None if cid in first_ids else via,
            )
        )
    return fused
