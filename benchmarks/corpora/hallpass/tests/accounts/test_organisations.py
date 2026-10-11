import pytest

from hallpass.accounts import organisations
from hallpass.accounts.roles import Principal
from hallpass.core.errors import ConflictError, Forbidden, NotFound, ValidationError


@pytest.fixture
def club(pg_conn, make_resident):
    chair = make_resident("chair@rovers.example.org", "Alex Chair")
    org_id = organisations.create(pg_conn, founder_resident_id=chair, name="Northgate Rovers FC",
                                  kind="club", billing_email="treasurer@rovers.example.org")
    return org_id, chair


def test_founder_is_org_admin(pg_conn, club):
    org_id, chair = club
    [row] = organisations.list_for_member(pg_conn, chair)
    assert (row["id"], row["role"], row["pays_by_invoice"]) == (org_id, "org_admin", False)


def test_add_member_by_email(pg_conn, club, make_resident):
    org_id, chair = club
    m = make_resident("player@example.org")
    out = organisations.add_member(pg_conn, org_id, actor_resident_id=chair, email="Player@example.org")
    assert out == {"organisation_id": org_id, "resident_id": m, "role": "member"}


def test_add_unknown_email(pg_conn, club):
    org_id, chair = club
    with pytest.raises(NotFound):
        organisations.add_member(pg_conn, org_id, actor_resident_id=chair, email="new@example.org")


def test_member_cannot_add_members(pg_conn, club, make_resident):
    org_id, chair = club
    m = make_resident("player@example.org")
    make_resident("friend@example.org")
    organisations.add_member(pg_conn, org_id, actor_resident_id=chair, email="player@example.org")
    with pytest.raises(Forbidden):
        organisations.add_member(pg_conn, org_id, actor_resident_id=m, email="friend@example.org")


def test_last_admin_cannot_leave(pg_conn, club):
    org_id, chair = club
    me = Principal(kind="resident", id=chair, role="resident")
    with pytest.raises(ConflictError):
        organisations.remove_member(pg_conn, org_id, chair, actor=me)


def test_superuser_can_remove_last_admin(pg_conn, club):
    org_id, chair = club
    organisations.remove_member(pg_conn, org_id, chair, actor=Principal(kind="staff", id=1, role="superuser"))
    assert organisations.list_for_member(pg_conn, chair) == []


def test_bad_kind(pg_conn, make_resident):
    with pytest.raises(ValidationError):
        organisations.create(pg_conn, founder_resident_id=make_resident(), name="Ltd Co",
                             kind="business", billing_email="a@example.org")
