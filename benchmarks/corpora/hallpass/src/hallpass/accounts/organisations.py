"""Organisations (clubs, charities, schools, community groups) and members.

Membership role is 'member' or 'org_admin'. Admins can add/remove members and
book for the org; members can see the org's upcoming bookings and get
closure notices, that's all.

Every org must keep at least one org_admin. Staff (superuser) can remove the
last one, e.g. when a club folds, which leaves it orphaned.

pays_by_invoice starts false. Finance switch it on after their own checks
(outside the system). charity_number is free text - not checked against the
Charity Commission register (HP-311, parked).
"""

from __future__ import annotations

from hallpass.accounts import residents
from hallpass.accounts.roles import Principal, require_org_admin
from hallpass.core import db
from hallpass.core.errors import ConflictError, NotFound, ValidationError

KINDS = ("club", "charity", "community_group", "school", "commercial")
MEMBER_ROLES = ("member", "org_admin")


def list_for_member(conn, resident_id: int) -> list[dict]:
    return db.fetch_all(
        conn,
        "SELECT o.id, o.name, o.kind, m.role, o.pays_by_invoice "
        "FROM organisation_members m JOIN organisations o ON o.id = m.organisation_id "
        "WHERE m.resident_id = %s ORDER BY o.name",
        (resident_id,),
    )


def create(conn, *, founder_resident_id: int, name: str, kind: str, billing_email: str,
           charity_number: str | None = None) -> int:
    name = name.strip()
    if not 2 <= len(name) <= 150:
        raise ValidationError("Organisation name must be 2-150 characters")
    if kind not in KINDS:
        raise ValidationError(f"unknown organisation type {kind!r}")
    row = db.fetch_one(
        conn,
        "INSERT INTO organisations (name, kind, charity_number, billing_email) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        (name, kind, charity_number, residents.normalise_email(billing_email)),
    )
    conn.execute(
        "INSERT INTO organisation_members (organisation_id, resident_id, role) VALUES (%s, %s, 'org_admin')",
        (row["id"], founder_resident_id),
    )
    return row["id"]


def add_member(conn, org_id: int, *, actor_resident_id: int, email: str, role: str = "member") -> dict:
    require_org_admin(conn, Principal(kind="resident", id=actor_resident_id, role="resident"), org_id)
    if role not in MEMBER_ROLES:
        raise ValidationError(f"unknown membership role {role!r}")
    person = residents.find_by_email(conn, email)
    if person is None:
        # They have to register themselves first. (No invite flow - known issue.)
        raise NotFound("No Hallpass account with that email. Ask them to register first.")
    conn.execute(
        "INSERT INTO organisation_members (organisation_id, resident_id, role) VALUES (%s, %s, %s) "
        "ON CONFLICT (organisation_id, resident_id) DO UPDATE SET role = EXCLUDED.role",
        (org_id, person["id"], role),
    )
    # TODO: tell them. outbox template 'org_member_added' was designed but never written.
    return {"organisation_id": org_id, "resident_id": person["id"], "role": role}


def remove_member(conn, org_id: int, resident_id: int, *, actor: Principal) -> None:
    require_org_admin(conn, actor, org_id)
    row = conn.execute(
        "SELECT role FROM organisation_members WHERE organisation_id = %s AND resident_id = %s FOR UPDATE",
        (org_id, resident_id),
    ).fetchone()
    if row is None:
        raise NotFound("not a member")
    (admins,) = conn.execute(
        "SELECT count(*) FROM organisation_members WHERE organisation_id = %s AND role = 'org_admin'",
        (org_id,),
    ).fetchone()
    if row[0] == "org_admin" and admins <= 1 and actor.kind != "staff":
        raise ConflictError("An organisation needs at least one admin")
    conn.execute(
        "DELETE FROM organisation_members WHERE organisation_id = %s AND resident_id = %s",
        (org_id, resident_id),
    )
    # FIXME: their future bookings for the org stay in their name, so the
    # ex-secretary keeps getting the reminders. Needs "transfer bookings".
