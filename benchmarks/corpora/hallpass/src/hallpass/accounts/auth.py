"""Emailed login links (ADR 0004).

Token = "<kind>.<account_id>.<issued_unix>.<nonce>.<sig>", sig being a
truncated HMAC-SHA256 with settings.secret_key. No tokens table.

Single use: a resident link is rejected if it was issued before the
resident's last_login_at. So using any link kills every older one. Staff
links are NOT single use - staff_users has no last_login_at column - they
just expire. (Known issue; needs a migration.)

TTL is settings.magic_link_ttl_minutes (20; it was 60 until the 2024 pen test).

The link is redeemed by GET /api/account/magic-link/<token>. Mail scanners
that pre-open links (Outlook Safe Links, Mimecast) therefore use them up
before the person clicks. See docs/known-issues/accounts-and-notifications.md.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
from datetime import UTC, datetime, timedelta

from hallpass.accounts import residents
from hallpass.accounts.roles import RESIDENT, Principal
from hallpass.core import clock
from hallpass.core.config import get_settings
from hallpass.core.errors import NotAuthenticated
from hallpass.notifications import outbox

log = logging.getLogger(__name__)

MAX_LINKS_PER_HOUR = 5  # per address, counted from the outbox


class InvalidLink(NotAuthenticated):
    default_code = "link_invalid"


def _sign(body: str) -> str:
    key = get_settings().secret_key.encode()
    mac = hmac.new(key, body.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac[:24]).decode().rstrip("=")


def make_token(kind: str, account_id: int, issued_at: datetime) -> str:
    body = f"{kind}.{account_id}.{int(issued_at.timestamp())}.{secrets.token_hex(4)}"
    return f"{body}.{_sign(body)}"


def parse_token(token: str) -> tuple[str, int, datetime]:
    try:
        kind, account_id, ts, nonce, sig = token.split(".")
        issued = datetime.fromtimestamp(int(ts), tz=UTC)
        account = int(account_id)
    except ValueError:
        raise InvalidLink("That login link isn't valid") from None
    if kind not in ("r", "s") or not hmac.compare_digest(sig, _sign(f"{kind}.{account_id}.{ts}.{nonce}")):
        raise InvalidLink("That login link isn't valid")
    return kind, account, issued


def _throttled(conn, email: str) -> bool:
    (n,) = conn.execute(
        "SELECT count(*) FROM notifications_outbox WHERE template IN ('magic_link', 'staff_magic_link') "
        "AND recipient = %s AND created_at > %s",
        (email, clock.now() - timedelta(hours=1)),
    ).fetchone()
    return n >= MAX_LINKS_PER_HOUR


def send_magic_link(conn, *, email: str, ip: str | None = None) -> None:
    """Queue a login link. Same response whether or not the address exists.

    Unknown addresses get nothing (they have to register first - residents
    need a full_name, so we can't create the row here). `ip` is only used for
    the log line; we used to rate-limit on it but the libraries all share one
    council IP and kept tripping it.
    """
    email = residents.normalise_email(email)
    if _throttled(conn, email):
        log.info("magic link throttled (ip=%s)", ip)
        return
    resident = residents.find_by_email(conn, email)
    if resident is not None:
        token = make_token("r", resident["id"], clock.now())
        outbox.enqueue(conn, template="magic_link", resident_id=resident["id"], context={"token": token})
        return
    staff = conn.execute(
        "SELECT id FROM staff_users WHERE email = %s AND active", (email,)
    ).fetchone()
    if staff is not None:
        token = make_token("s", staff[0], clock.now())
        outbox.enqueue(conn, template="staff_magic_link", to_email=email, context={"token": token})


def verify_magic_link(conn, token: str) -> Principal:
    kind, account_id, issued = parse_token(token)
    now = clock.now()
    ttl = timedelta(minutes=get_settings().magic_link_ttl_minutes)
    if now - issued > ttl or issued > now + timedelta(minutes=2):
        raise InvalidLink("That login link has expired. Ask for a new one.")

    if kind == "s":
        row = conn.execute("SELECT role FROM staff_users WHERE id = %s AND active", (account_id,)).fetchone()
        if row is None:
            raise InvalidLink("That login link isn't valid")
        return Principal(kind="staff", id=account_id, role=row[0])

    # FOR UPDATE: two tabs opening the same link can't both win.
    row = conn.execute(
        "SELECT last_login_at FROM residents WHERE id = %s AND deleted_at IS NULL FOR UPDATE",
        (account_id,),
    ).fetchone()
    if row is None:
        raise InvalidLink("That login link isn't valid")
    # Token time is whole seconds and last_login_at isn't, so a link issued in
    # the same second as the previous login is rejected. Only bites in tests.
    if row[0] is not None and issued <= row[0]:
        raise InvalidLink("That login link has already been used. Use the newest email we sent.")
    conn.execute("UPDATE residents SET last_login_at = %s WHERE id = %s", (now, account_id))
    return Principal(kind="resident", id=account_id, role=RESIDENT)
