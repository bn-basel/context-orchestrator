"""Exception types that the API layer knows how to turn into HTTP responses.

Domain code raises these; hallpass.api.app maps them to status codes in one
place. Don't raise werkzeug HTTPExceptions from domain packages.
"""

from __future__ import annotations


class HallpassError(Exception):
    status = 500
    default_code = "internal_error"

    def __init__(self, message: str, *, code: str | None = None, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code
        self.details = details or {}

    def to_dict(self) -> dict:
        body = {"error": self.code, "message": self.message}
        if self.details:
            body["details"] = self.details
        return body


class ValidationError(HallpassError):
    status = 400
    default_code = "invalid"


class NotAuthenticated(HallpassError):
    status = 401
    default_code = "not_authenticated"


class Forbidden(HallpassError):
    status = 403
    default_code = "forbidden"


class PermissionDenied(Forbidden):
    """Signed in, but the role doesn't allow it. Raised by accounts.roles."""

    default_code = "permission_denied"


class NotFound(HallpassError):
    status = 404
    default_code = "not_found"


class ConflictError(HallpassError):
    """Double booking, stale state transitions, duplicate submissions."""

    status = 409
    default_code = "conflict"


# Short alias; accounts code uses this name.
Conflict = ConflictError


class PolicyError(HallpassError):
    """Request is well-formed but breaks a business rule (too far ahead,
    outside opening hours, refund window passed...)."""

    status = 422
    default_code = "policy"


class UpstreamError(HallpassError):
    """Paybridge / TextHub / SMTP relay misbehaving."""

    status = 502
    default_code = "upstream"

    def __init__(self, message: str, *, provider: str, **kwargs):
        super().__init__(message, **kwargs)
        self.provider = provider
