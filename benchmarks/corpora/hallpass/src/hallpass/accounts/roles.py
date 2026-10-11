"""Roles and access checks.

Five roles. Two are hirer-side, three come from staff_users.role:

    resident        anyone signed in with a row in `residents`
    org_admin       a resident with organisation_members.role = 'org_admin'
                    for a particular organisation. Scoped - you're an admin
                    *of* something, never globally.
    facility_staff  duty managers / reception at the centres and halls
    finance         Leisure Services finance officers
    superuser       dev team + two service desk leads

There is no permissions table. Each endpoint lists the roles it accepts
(`require_role(who, "finance", "superuser")`). We tried a numeric level in
2023 and it went badly: finance must see refunds but not edit closures,
facility staff need closures but not money. docs/accounts/roles.md has the
matrix of what each endpoint accepts - keep it in step.

superuser is NOT implied: endpoints spell it out. That's deliberate (grep
for an endpoint without "superuser" and you've found something even we
can't do from the UI), but it confuses everyone once.
"""

from __future__ import annotations

from dataclasses import dataclass

from hallpass.core.errors import Forbidden, NotAuthenticated

RESIDENT = "resident"
ORG_ADMIN = "org_admin"
FACILITY_STAFF = "facility_staff"
FINANCE = "finance"
SUPERUSER = "superuser"

STAFF_ROLES = (FACILITY_STAFF, FINANCE, SUPERUSER)
ALL_ROLES = (RESIDENT, ORG_ADMIN, *STAFF_ROLES)


@dataclass(frozen=True)
class Principal:
    """Who is making the request. Built by sessions.load_principal.

    kind is "resident" or "staff". For staff, `role` is their staff role;
    for residents it's always "resident" (org_admin is checked per org).
    """

    kind: str
    id: int
    role: str
    impersonated_by: int | None = None  # staff id when a superuser "views as"


def require_role(who: Principal | None, *roles: str) -> Principal:
    if who is None:
        raise NotAuthenticated("sign in to continue")
    if who.role not in roles:
        raise Forbidden(f"needs one of: {', '.join(roles)}")
    return who


def is_org_admin(conn, who: Principal, organisation_id: int) -> bool:
    if who.kind != "resident":
        return False
    row = conn.execute(
        "SELECT 1 FROM organisation_members "
        "WHERE organisation_id = %s AND resident_id = %s AND role = 'org_admin'",
        (organisation_id, who.id),
    ).fetchone()
    return row is not None


def require_org_admin(conn, who: Principal | None, organisation_id: int) -> Principal:
    """Org admin of *this* organisation, or a superuser.

    Facility staff can book on an org's behalf (phone bookings) but cannot
    change its members; that goes through require_role, not here.
    """
    if who is None:
        raise NotAuthenticated("sign in to continue")
    if who.kind == "staff" and who.role == SUPERUSER:
        return who
    if not is_org_admin(conn, who, organisation_id):
        raise Forbidden("organisation admins only")
    return who
