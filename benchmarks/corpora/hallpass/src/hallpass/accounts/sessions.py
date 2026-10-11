"""Session cookie <-> Principal.

Cookie value: "<kind>:<id>:<expires_unix>[:<impersonator_id>]:<sig>", signed
with settings.secret_key. No server-side session store.

Residents: 30 days. Staff: 12 hours (council IT policy ISP-07 - anything
showing personal data).

Consequence of having no store: we can't log a resident out "everywhere".
Staff are re-checked against staff_users.active on every request, so
disabling a staff account works immediately; there is no equivalent for
residents. Rotating secret_key logs out *everyone*, which we've done once.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import timedelta

from hallpass.accounts.roles import RESIDENT, Principal
from hallpass.core import clock, db
from hallpass.core.config import get_settings

COOKIE_NAME = "hp_session"
RESIDENT_TTL = timedelta(days=30)
STAFF_TTL = timedelta(hours=12)


def _sig(body: str) -> str:
    return hmac.new(get_settings().secret_key.encode(), body.encode(), hashlib.sha256).hexdigest()[:32]


def encode(who: Principal) -> str:
    ttl = STAFF_TTL if who.kind == "staff" else RESIDENT_TTL
    parts = [who.kind, str(who.id), str(int((clock.now() + ttl).timestamp()))]
    if who.impersonated_by is not None:
        parts.append(str(who.impersonated_by))
    body = ":".join(parts)
    return f"{body}:{_sig(body)}"


def decode(value: str) -> tuple[str, int, int | None] | None:
    *parts, sig = value.split(":")
    body = ":".join(parts)
    if len(parts) not in (3, 4) or not hmac.compare_digest(sig, _sig(body)):
        return None
    try:
        kind, account_id, expires = parts[0], int(parts[1]), int(parts[2])
        impersonator = int(parts[3]) if len(parts) == 4 else None
    except ValueError:
        return None
    if expires <= clock.now().timestamp() or kind not in ("resident", "staff"):
        return None
    return kind, account_id, impersonator


def load_principal(request) -> Principal | None:
    raw = request.cookies.get(COOKIE_NAME)
    decoded = decode(raw) if raw else None
    if decoded is None:
        return None
    kind, account_id, impersonator = decoded
    if kind == "resident":
        return Principal(kind=kind, id=account_id, role=RESIDENT, impersonated_by=impersonator)
    with db.connection() as conn:
        row = conn.execute("SELECT role FROM staff_users WHERE id = %s AND active", (account_id,)).fetchone()
    if row is None:
        return None
    return Principal(kind="staff", id=account_id, role=row[0])


def set_session_cookie(resp, who: Principal) -> None:
    max_age = STAFF_TTL if who.kind == "staff" else RESIDENT_TTL
    resp.set_cookie(
        COOKIE_NAME,
        encode(who),
        max_age=int(max_age.total_seconds()),
        secure=get_settings().is_production,
        httponly=True,
        samesite="Lax",
    )


def clear_session_cookie(resp) -> None:
    resp.delete_cookie(COOKIE_NAME)
