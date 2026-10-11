"""Core data types shared by every module.

These types are the request/response contract between agents and the context
service. They are plain dataclasses so they serialise to JSON without a
framework and can be validated in tests.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

DEFAULT_MIN_RELATIVE_SCORE = 0.0
DEFAULT_MAX_REFERENCES = 0
DEFAULT_HOPS = 1
DEFAULT_DETAIL = "full"
DEFAULT_MAX_FINDINGS = 3
DETAIL_LEVELS = ("full", "compact")


class InfoKind(StrEnum):
    """Categories of project knowledge an agent can ask for."""

    DECISION = "decision"  # architecture / design decisions (ADRs)
    SCHEMA = "schema"  # database schemas, data models
    CONVENTION = "convention"  # coding conventions, style rules
    CODE = "code"  # source files and excerpts
    TEST = "test"  # existing tests
    DEPENDENCY = "dependency"  # dependency manifests
    CONSTRAINT = "constraint"  # non-functional constraints, limits, policies
    KNOWN_ISSUE = "known_issue"  # known bugs
    FINDING = "finding"  # previously verified findings
    DOC = "doc"  # any other documentation


class Status(StrEnum):
    """How much the knowledge base vouches for a piece of information.

    ``OBSERVED`` means the text was read directly from a source file (code,
    schema, manifest): it shows what exists, not that it is correct.
    Documents declare the other statuses in their front matter; documents that
    declare nothing are ``UNVERIFIED``.
    """

    VERIFIED = "verified"
    OBSERVED = "observed"
    UNVERIFIED = "unverified"
    ASSUMPTION = "assumption"
    SUPERSEDED = "superseded"


class MetricKind(StrEnum):
    """Provenance of a number. Missing data is UNAVAILABLE, never zero."""

    MEASURED = "measured"
    ESTIMATED = "estimated"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class Metric:
    value: float | int | None
    kind: MetricKind
    method: str

    @classmethod
    def measured(cls, value: float | int, method: str) -> Metric:
        return cls(value, MetricKind.MEASURED, method)

    @classmethod
    def estimated(cls, value: float | int, method: str) -> Metric:
        return cls(value, MetricKind.ESTIMATED, method)

    @classmethod
    def unavailable(cls, method: str) -> Metric:
        return cls(None, MetricKind.UNAVAILABLE, method)


@dataclass(frozen=True, slots=True)
class SourceRef:
    """Where a piece of context came from, precise enough to re-open it."""

    path: str  # POSIX-style, relative to the project root
    line_start: int  # 1-based, inclusive
    line_end: int  # 1-based, inclusive
    file_sha256: str  # hash of the whole file at ingestion time
    ingested_at: str  # ISO-8601 UTC

    def label(self) -> str:
        return f"{self.path}:{self.line_start}-{self.line_end}"


@dataclass(frozen=True, slots=True)
class Chunk:
    """A retrievable unit of project knowledge."""

    chunk_id: str
    kind: InfoKind
    status: Status
    heading: str
    text: str
    source: SourceRef
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Finding:
    """Something an agent learned about the project, anchored to the lines that show it.

    ``evidence`` is a verbatim quote from the cited lines, checked when the
    finding is recorded, so a finding cannot cite lines that do not say it.
    ``source.file_sha256`` is the file's hash at that moment: if the file has
    changed since, the finding is reported as stale. ``source.ingested_at``
    holds the recording time. ``review`` stays "unreviewed" until a person
    confirms it; until then the claim is labelled unverified.
    """

    finding_id: str
    claim: str
    evidence: str
    source: SourceRef
    agent_id: str
    review: str = "unreviewed"


@dataclass(slots=True)
class ContextRequest:
    """What an agent asks the context service for."""

    task: str
    kinds: list[InfoKind] = field(default_factory=list)  # empty = any kind
    constraints: list[str] = field(default_factory=list)
    agent_id: str = "anonymous"
    max_tokens: int = 4000
    per_kind_limit: int = 3
    # Drop hits scoring below this fraction of the query's best hit (any kind). A requested
    # kind left with only such weak hits is reported as unresolved. 0 disables the filter.
    min_relative_score: float = DEFAULT_MIN_RELATIVE_SCORE
    # After search, add up to this many code/test chunks that define functions or classes
    # named in the selected items (budget permitting, requested kinds only). 0 disables.
    max_references: int = DEFAULT_MAX_REFERENCES
    # 2 = search again for the functions, classes and tables the top results name, and
    # fuse both rankings (see retrieval.multihop). 1 = a single search.
    hops: int = DEFAULT_HOPS
    # "compact": each item shows only its first few lines (signature, docstring, opening
    # of a section) plus where it is, so a budget holds more pointers; the agent reads the
    # rest from the file. "full": the whole chunk.
    detail: str = DEFAULT_DETAIL
    include_superseded: bool = False
    # Findings recorded by earlier agents (anchored, unreviewed) placed before search
    # results. 0 disables them.
    max_findings: int = DEFAULT_MAX_FINDINGS
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContextRequest:
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        if "task" not in known or not str(known["task"]).strip():
            raise ValueError("ContextRequest requires a non-empty 'task'")
        known["kinds"] = [InfoKind(k) for k in known.get("kinds", [])]
        if known.get("detail", DEFAULT_DETAIL) not in DETAIL_LEVELS:
            raise ValueError(f"detail must be one of {DETAIL_LEVELS}")
        return cls(**known)


@dataclass(frozen=True, slots=True)
class ContextItem:
    """One retrieved piece of context, with the evidence for including it."""

    kind: InfoKind
    status: Status
    heading: str
    text: str
    source: SourceRef
    score: float  # BM25 relevance (higher is better); comparable within one query only
    matched_terms: tuple[str, ...]
    stale: bool | None  # True if the file changed since ingestion; None if not checked
    estimated_tokens: int  # of this item's rendered block (heading, flags and text)
    via: str | None = None  # why it was added when not by search, e.g. "referenced by …"
    similarity: float | None = None  # cosine similarity to the task, when vectors were used
    excerpt_lines: tuple[int, int] | None = None  # set when only part of the chunk is shown


@dataclass(frozen=True, slots=True)
class OmittedItem:
    source: SourceRef
    reason: str


@dataclass(slots=True)
class ContextPackage:
    """The context service's answer to a ContextRequest."""

    request_id: str
    task: str
    items: list[ContextItem]
    unresolved: list[str]
    omitted: list[OmittedItem]
    estimated_tokens: Metric
    query_terms: list[str]
    notes: list[str] = field(default_factory=list)
    # Requested kinds with no match ("any" when no kinds were requested); machine-readable
    # counterpart of the matching sentences in ``unresolved``.
    unresolved_kinds: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def render_markdown(self) -> str:
        """Render the package as the text an agent would put in its prompt.

        The text is the concatenation of independently rendered blocks, so the
        orchestrator can budget each block before the package exists.
        """
        return (
            render_header(self.task)
            + "".join(render_item(item) for item in self.items)
            + render_unresolved(self.unresolved)
        )


def render_header(task: str) -> str:
    return f"# Context package for: {task}\n\n"


def render_item(item: ContextItem) -> str:
    flags = [item.kind.value, item.status.value]
    if item.stale:
        since = "it was recorded" if item.kind is InfoKind.FINDING else "ingestion"
        flags.append(f"STALE: file changed since {since}")
    if item.via:
        flags.append(item.via)
    more = ""
    if item.excerpt_lines:
        first, last = item.excerpt_lines
        more = (
            f"… (excerpt: lines {first}-{last} of {item.source.line_start}-"
            f"{item.source.line_end}; read the file for the rest)\n"
        )
    return (
        f"## {item.heading}  ({item.source.label()})\n"
        f"_[{', '.join(flags)}]_\n\n"
        f"{item.text.rstrip()}\n{more}\n"
    )


def render_unresolved(unresolved: list[str]) -> str:
    if not unresolved:
        return ""
    return "## Unresolved\n" + "".join(f"- {q}\n" for q in unresolved) + "\n"
