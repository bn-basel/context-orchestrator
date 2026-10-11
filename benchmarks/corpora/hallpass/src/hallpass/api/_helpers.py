"""Small request helpers shared by the blueprints."""

from __future__ import annotations

import dataclasses
import enum
from datetime import date, datetime, time
from typing import Any

from flask import g, jsonify, request

from hallpass.core.errors import NotAuthenticated, ValidationError


def json_body() -> dict[str, Any]:
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("expected a JSON object body")
    return body


def require_resident():
    p = g.get("principal")
    if p is None or p.kind != "resident":
        raise NotAuthenticated("sign in to continue")
    return p


def require_staff():
    p = g.get("principal")
    if p is None or p.kind != "staff":
        raise NotAuthenticated("staff sign-in required")
    return p


def parse_date(value: str | None, field: str) -> date:
    if not value:
        raise ValidationError(f"{field} is required", details={"field": field})
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(f"{field} must be YYYY-MM-DD", details={"field": field}) from exc


def parse_time(value: str | None, field: str) -> time:
    if not value:
        raise ValidationError(f"{field} is required", details={"field": field})
    try:
        return time.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(f"{field} must be HH:MM", details={"field": field}) from exc


def parse_instant(value: str | None, field: str) -> datetime:
    """ISO 8601 with offset. Naive strings are rejected, we won't guess."""
    if not value:
        raise ValidationError(f"{field} is required", details={"field": field})
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(f"{field} is not an ISO timestamp", details={"field": field}) from exc
    if dt.tzinfo is None:
        raise ValidationError(f"{field} needs a UTC offset", details={"field": field})
    return dt


def int_arg(name: str, default: int | None = None) -> int | None:
    raw = request.args.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValidationError(f"{name} must be an integer") from exc


def _plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {k: _plain(v) for k, v in dataclasses.asdict(value).items()}
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def to_json(obj: Any, status: int = 200):
    """Domain functions return dataclasses; Flask's jsonify doesn't know
    about those (or about our StrEnums in older Flask)."""
    return jsonify(_plain(obj)), status
