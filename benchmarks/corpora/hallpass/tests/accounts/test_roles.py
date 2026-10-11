import pytest

from hallpass.accounts import organisations
from hallpass.accounts.roles import (
    ALL_ROLES,
    Principal,
    require_org_admin,
    require_role,
)
from hallpass.core.errors import Forbidden, NotAuthenticated


def staff(role, id=1):
    return Principal(kind="staff", id=id, role=role)


def test_five_roles():
    assert set(ALL_ROLES) == {"resident", "org_admin", "facility_staff", "finance", "superuser"}


def test_require_role_accepts_listed_role():
    assert require_role(staff("finance"), "finance", "superuser").role == "finance"


def test_superuser_is_not_implied():
    # Endpoints list superuser explicitly; require_role doesn't add it.
    with pytest.raises(Forbidden):
        require_role(staff("superuser"), "facility_staff")


def test_anonymous_gets_401_not_403():
    with pytest.raises(NotAuthenticated):
        require_role(None, "finance")


@pytest.mark.parametrize("role", ["facility_staff", "resident"])
def test_refund_roles_exclude_facility_staff_and_residents(role):
    who = Principal(kind="resident", id=5, role="resident") if role == "resident" else staff(role)
    with pytest.raises(Forbidden):
        require_role(who, "finance", "superuser")


def test_org_admin_is_scoped(pg_conn, make_resident):
    chair = make_resident("chair@rovers.example.org")
    rovers = organisations.create(pg_conn, founder_resident_id=chair, name="Northgate Rovers FC",
                                  kind="club", billing_email="treasurer@rovers.example.org")
    other_chair = make_resident("sec@allotments.example.org")
    allotments = organisations.create(pg_conn, founder_resident_id=other_chair, name="Eastfield Allotment Society",
                                      kind="community_group", billing_email="sec@allotments.example.org")
    me = Principal(kind="resident", id=chair, role="resident")
    assert require_org_admin(pg_conn, me, rovers) is me
    with pytest.raises(Forbidden):
        require_org_admin(pg_conn, me, allotments)


def test_facility_staff_cannot_act_as_org_admin(pg_conn, make_resident):
    chair = make_resident()
    org = organisations.create(pg_conn, founder_resident_id=chair, name="Badminton Club",
                               kind="club", billing_email="b@example.org")
    with pytest.raises(Forbidden):
        require_org_admin(pg_conn, staff("facility_staff"), org)
    assert require_org_admin(pg_conn, staff("superuser"), org).role == "superuser"
