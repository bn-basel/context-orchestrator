from datetime import timedelta

import pytest

from hallpass.accounts import auth
from hallpass.accounts.auth import InvalidLink
from tests.accounts.conftest import T0


def _links(pg_conn, email):
    return pg_conn.execute(
        "SELECT template, context FROM notifications_outbox WHERE recipient = %s ORDER BY id", (email,)
    ).fetchall()


def test_known_resident_gets_a_link(pg_conn, frozen, make_resident):
    make_resident("sam@example.org")
    auth.send_magic_link(pg_conn, email="  Sam@Example.org ", ip="10.0.0.1")
    [(template, ctx)] = _links(pg_conn, "sam@example.org")
    assert template == "magic_link"
    assert ctx["token"].startswith("r.")


def test_unknown_address_gets_nothing_and_no_error(pg_conn, frozen):
    auth.send_magic_link(pg_conn, email="nobody@example.org")
    assert _links(pg_conn, "nobody@example.org") == []


def test_throttle_is_silent(pg_conn, frozen, make_resident):
    make_resident("keen@example.org")
    for _ in range(auth.MAX_LINKS_PER_HOUR + 3):
        auth.send_magic_link(pg_conn, email="keen@example.org")
    assert len(_links(pg_conn, "keen@example.org")) == auth.MAX_LINKS_PER_HOUR


def test_redeem_once(pg_conn, frozen, make_resident):
    rid = make_resident()
    token = auth.make_token("r", rid, T0)
    frozen(T0 + timedelta(minutes=2))
    assert auth.verify_magic_link(pg_conn, token).id == rid
    with pytest.raises(InvalidLink):
        auth.verify_magic_link(pg_conn, token)


def test_using_newer_link_kills_older_one(pg_conn, frozen, make_resident):
    rid = make_resident()
    old = auth.make_token("r", rid, T0)
    new = auth.make_token("r", rid, T0 + timedelta(minutes=1))
    frozen(T0 + timedelta(minutes=2))
    auth.verify_magic_link(pg_conn, new)
    with pytest.raises(InvalidLink):
        auth.verify_magic_link(pg_conn, old)


def test_expires_after_20_minutes(pg_conn, frozen, make_resident):
    rid = make_resident()
    token = auth.make_token("r", rid, T0)
    frozen(T0 + timedelta(minutes=21))
    with pytest.raises(InvalidLink):
        auth.verify_magic_link(pg_conn, token)


def test_tampered_token(pg_conn, frozen, make_resident):
    rid = make_resident()
    kind, _id, rest = auth.make_token("r", rid, T0).split(".", 2)
    with pytest.raises(InvalidLink):
        auth.verify_magic_link(pg_conn, f"{kind}.{rid + 1}.{rest}")


def test_inactive_staff_cannot_log_in(pg_conn, frozen, make_staff):
    sid = make_staff(active=False)
    with pytest.raises(InvalidLink):
        auth.verify_magic_link(pg_conn, auth.make_token("s", sid, T0))


def test_staff_link_can_be_reused_within_ttl(pg_conn, frozen, make_staff):
    # Documents the known gap: no last_login_at on staff_users.
    sid = make_staff(role="finance")
    token = auth.make_token("s", sid, T0)
    assert auth.verify_magic_link(pg_conn, token).role == "finance"
    assert auth.verify_magic_link(pg_conn, token).role == "finance"
