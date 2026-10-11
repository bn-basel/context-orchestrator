"""Sign in (magic link), profile, organisations, consents."""

from __future__ import annotations

from flask import Blueprint, g, jsonify, make_response, request

from hallpass.accounts import auth, consents, organisations, residents, sessions
from hallpass.accounts.roles import require_org_admin
from hallpass.api._helpers import json_body, require_resident, to_json
from hallpass.core import db
from hallpass.core.clock import system_clock
from hallpass.core.config import get_settings
from hallpass.core.errors import NotFound, ValidationError

bp = Blueprint("accounts", __name__)


def _set_cookie(resp, session: sessions.Session) -> None:
    resp.set_cookie(
        sessions.COOKIE_NAME,
        sessions.encode(session),
        expires=session.expires_at,
        secure=get_settings().is_production,
        httponly=True,
        samesite="Lax",
    )


@bp.post("/magic-link")
def request_magic_link():
    body = json_body()
    with db.transaction() as conn:
        # Same response whether or not the email exists (no account probing).
        auth.request_link(conn, str(body.get("email", "")), system_clock, next_path=body.get("next", "/"))
    return jsonify({"sent": True}), 202


@bp.get("/magic-link/<token>")
def redeem_magic_link(token: str):
    with db.transaction() as conn:
        redeemed = auth.redeem(conn, token, system_clock)
        session = sessions.start(conn, redeemed.subject, redeemed.account_id, system_clock)
    resp = make_response(jsonify({"signed_in": True}))
    _set_cookie(resp, session)
    return resp


@bp.post("/logout")
def logout():
    resp = make_response(jsonify({"signed_out": True}))
    resp.delete_cookie(sessions.COOKIE_NAME)
    return resp


@bp.post("/logout-everywhere")
def logout_everywhere():
    who = require_resident()
    with db.transaction() as conn:
        residents.bump_session_epoch(conn, who.id)
    resp = make_response(jsonify({"signed_out": True}))
    resp.delete_cookie(sessions.COOKIE_NAME)
    return resp


@bp.get("/me")
def me():
    who = require_resident()
    with db.connection() as conn:
        return to_json(residents.get(conn, who.id))


@bp.patch("/me")
def update_me():
    who = require_resident()
    body = json_body()
    with db.transaction() as conn:
        residents.update_profile(
            conn,
            who.id,
            display_name=body.get("display_name"),
            mobile=body.get("mobile"),
            postcode=body.get("postcode"),
        )
        return to_json(residents.get(conn, who.id))


@bp.put("/me/consents/<purpose>")
def set_consent(purpose: str):
    who = require_resident()
    body = json_body()
    try:
        p = consents.Purpose(purpose)
    except ValueError as exc:
        raise ValidationError(f"unknown consent purpose {purpose!r}") from exc
    granted = bool(body.get("granted"))
    with db.transaction() as conn:
        consents.record(conn, who.id, p, granted, source="profile_page", clock=system_clock)
    return jsonify({"purpose": purpose, "granted": granted})


@bp.get("/organisations/<int:org_id>/members")
def list_members(org_id: int):
    who = require_resident()
    with db.connection() as conn:
        require_org_admin(conn, who, org_id)
        rows = organisations.list_members(conn, org_id)
    return jsonify([{"resident_id": r[0], "name": r[1], "role": r[2]} for r in rows])


@bp.post("/organisations/<int:org_id>/members")
def add_member(org_id: int):
    require_resident()
    body = json_body()
    with db.transaction() as conn:
        target = residents.find_by_email(conn, str(body.get("email", "")))
        if target is None:
            # They have to have signed in at least once. The org admin UI
            # tells them to ask the person to request a link first.
            raise NotFound("no account with that email yet")
        organisations.add_member(conn, g.principal, org_id, target.id, body.get("role", "member"), system_clock)
    return jsonify({"added": True}), 201


@bp.delete("/organisations/<int:org_id>/members/<int:resident_id>")
def remove_member(org_id: int, resident_id: int):
    require_resident()
    force = request.args.get("force") == "1"
    with db.transaction() as conn:
        organisations.remove_member(conn, g.principal, org_id, resident_id, system_clock, force=force)
    return jsonify({"removed": True})
