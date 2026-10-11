"""Feature flags backed by the ``feature_flags`` table (ADR 0014).

    from hallpass.core import flags
    if flags.is_enabled("waitlist", facility_id=space["facility_id"]):
        ...

Values are cached per process for FLAG_CACHE_SECONDS so we don't hit the DB
on every request. That means a flip in the back office takes up to a minute
to reach every gunicorn worker. The cron worker is a fresh process each run so
it always sees the current value.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Any

from hallpass.core import db
from hallpass.core.audit import write_audit

log = logging.getLogger(__name__)

FLAG_CACHE_SECONDS = 60

_cache: dict[str, "Flag"] = {}
_loaded_at: float = 0.0


@dataclass(frozen=True)
class Flag:
    key: str
    enabled: bool
    rollout_percent: int
    facility_ids: tuple[int, ...] | None


def _load() -> None:
    global _cache, _loaded_at
    with db.connection() as conn:
        rows = db.fetch_all(
            conn,
            "SELECT key, enabled, rollout_percent, facility_ids FROM feature_flags",
        )
    _cache = {
        r["key"]: Flag(
            key=r["key"],
            enabled=r["enabled"],
            rollout_percent=r["rollout_percent"],
            facility_ids=tuple(r["facility_ids"]) if r["facility_ids"] is not None else None,
        )
        for r in rows
    }
    _loaded_at = time.monotonic()


def _bucket(key: str, subject: str) -> int:
    digest = hashlib.sha256(f"{key}:{subject}".encode()).digest()
    return int.from_bytes(digest[:2], "big") % 100


def is_enabled(*args: Any, facility_id: int | None = None, subject: str | int | None = None) -> bool:
    """``is_enabled(key)`` or, older style, ``is_enabled(conn, key)``.

    Unknown flags are OFF. ``subject`` (usually resident id) drives the
    percentage rollout so the same person gets a stable answer.

    The conn-first form exists because notifications was written against the
    first draft of this module. The connection is ignored (we use the pool);
    TODO: migrate the callers and drop it.
    """
    if len(args) == 2:
        _conn, key = args
    elif len(args) == 1:
        (key,) = args
    else:
        raise TypeError("is_enabled(key) or is_enabled(conn, key)")
    if time.monotonic() - _loaded_at > FLAG_CACHE_SECONDS:
        try:
            _load()
        except Exception:  # noqa: BLE001 - DB blip shouldn't take the site down
            log.exception("could not refresh feature flags; using cached values")
    flag = _cache.get(key)
    if flag is None or not flag.enabled:
        return False
    if flag.facility_ids is not None and facility_id not in flag.facility_ids:
        return False
    if flag.rollout_percent >= 100:
        return True
    if subject is None:
        return False
    return _bucket(key, str(subject)) < flag.rollout_percent


def set_flag(conn, key: str, enabled: bool, *, staff_id: int) -> None:
    """Back office toggle. Writes an audit_log row in the same transaction."""
    db.execute(
        conn,
        "UPDATE feature_flags SET enabled = %(enabled)s, updated_by = %(staff)s, updated_at = now()"
        " WHERE key = %(key)s",
        {"enabled": enabled, "staff": staff_id, "key": key},
    )
    write_audit(
        conn,
        actor_staff_id=staff_id,
        action="feature_flag.set",
        entity="feature_flags",
        detail={"key": key, "enabled": enabled},
    )
    invalidate()


def invalidate() -> None:
    global _loaded_at
    _loaded_at = 0.0
