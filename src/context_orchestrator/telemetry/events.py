"""Structured telemetry as append-only JSONL.

Privacy defaults: events never contain retrieved text, and the task text and
derived query terms are left out unless ``record_task_text=True``. Only a
SHA-256 of the task is stored, so repeated tasks can still be grouped.

Every numeric metric is a ``Metric`` carrying its provenance (measured,
estimated or unavailable) so later analysis cannot confuse them.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from context_orchestrator.models import ContextPackage, ContextRequest, Metric

log = logging.getLogger(__name__)

EVENT_SCHEMA_VERSION = 1


class TelemetrySink(Protocol):
    def emit(self, event: dict[str, Any]) -> None: ...


class NullTelemetry:
    def emit(self, event: dict[str, Any]) -> None:
        pass


class MemoryTelemetry:
    """Keeps events in a list; useful for tests and in-process experiments."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def emit(self, event: dict[str, Any]) -> None:
        self.events.append(event)


class JsonlTelemetry:
    def __init__(self, path: Path | str, record_task_text: bool = False) -> None:
        self.path = Path(path)
        self.record_task_text = record_task_text
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event: dict[str, Any]) -> None:
        if not self.record_task_text:
            event = {k: v for k, v in event.items() if k not in _SENSITIVE_KEYS}
        try:
            with self.path.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")
        except OSError:
            # Telemetry must never break a context request.
            log.exception("could not write telemetry to %s", self.path)


_SENSITIVE_KEYS = {"task", "query_terms", "constraints"}


def _metric(m: Metric) -> dict[str, Any]:
    return asdict(m)


def context_request_event(
    request: ContextRequest,
    package: ContextPackage,
    latency_ms: float,
    candidates_seen: int,
) -> dict[str, Any]:
    """Build the event for one handled context request.

    Includes the task text under sensitive keys; sinks strip them by default.
    """
    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "event": "context_request",
        "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
        "request_id": request.request_id,
        "agent_id": request.agent_id,
        "task_sha256": hashlib.sha256(request.task.encode("utf-8")).hexdigest(),
        "task": request.task,
        "constraints": list(request.constraints),
        "query_terms": list(package.query_terms),
        "requested_kinds": [k.value for k in request.kinds],
        "max_tokens": request.max_tokens,
        "candidates_seen": candidates_seen,
        "items_returned": len(package.items),
        "items_omitted": len(package.omitted),
        "unresolved_count": len(package.unresolved),
        "stale_count": sum(1 for i in package.items if i.stale),
        "statuses": sorted({i.status.value for i in package.items}),
        "sources": [i.source.label() for i in package.items],
        "latency_ms": _metric(
            Metric.measured(round(latency_ms, 3), "time.perf_counter in-process")
        ),
        "package_tokens": _metric(package.estimated_tokens),
    }
