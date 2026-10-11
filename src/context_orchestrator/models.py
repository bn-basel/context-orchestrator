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


@dataclass(slots=True)
class ContextRequest:
    """What an agent asks the context service for."""

    task: str
    kinds: list[InfoKind] = field(default_factory=list)  # empty = any kind
    constraints: list[str] = field(default_factory=list)
    agent_id: str = "anonymous"
    max_tokens: int = 4000
    per_kind_limit: int = 3
    include_superseded: bool = False
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContextRequest:
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        if "task" not in known or not str(known["task"]).strip():
            raise ValueError("ContextRequest requires a non-empty 'task'")
        known["kinds"] = [InfoKind(k) for k in known.get("kinds", [])]
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
    estimated_tokens: int


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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def render_markdown(self) -> str:
        """Render the package as the text an agent would put in its prompt."""
        lines = [f"# Context package for: {self.task}", ""]
        for item in self.items:
            flags = [item.kind.value, item.status.value]
            if item.stale:
                flags.append("STALE: file changed since ingestion")
            lines.append(f"## {item.heading}  ({item.source.label()})")
            lines.append(f"_[{', '.join(flags)}]_")
            lines.append("")
            lines.append(item.text.rstrip())
            lines.append("")
        if self.unresolved:
            lines.append("## Unresolved")
            lines.extend(f"- {q}" for q in self.unresolved)
            lines.append("")
        return "\n".join(lines)
