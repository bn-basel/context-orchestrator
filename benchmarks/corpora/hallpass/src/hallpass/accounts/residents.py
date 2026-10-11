"""Residents - a.k.a. customers, hirers, account holders.

Registration takes email + full name (+ optional phone and postcode), then
sends the first login link. Emails are citext in the DB so case doesn't
matter; we still strip whitespace. No gmail dot-folding - two different people
really did have j.smith@ and jsmith@ once.

`is_in_borough` drives resident pricing (billing reads it). It's set from
the postcode against the borough postcode list; out-of-date list = wrong
price. The list was last refreshed... ask Joanna.
"""

from __future__ import annotations

import re

from hallpass.accounts import consents
from hallpass.core import db
from hallpass.core.errors import ConflictError, NotFound, ValidationError

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
UK_MOBILE_RE = re.compile(r"^(?:\+44|0)7\d{9}$")  # TextHub can do abroad; council won't pay for it
EDITABLE = ("full_name", "phone", "postcode")


def normalise_email(raw: str) -> str:
    email = raw.strip().lower()
    if not EMAIL_RE.match(email):
        raise ValidationError("That doesn't look like an email address", details={"field": "email"})
    return email


def normalise_phone(raw: str | None) -> str | None:
    """'07700 900123' -> '+447700900123'. Blank -> None. Landlines are refused."""
    cleaned = re.sub(r"[\s\-()]", "", raw or "")
    if not cleaned:
        return None
    if not UK_MOBILE_RE.match(cleaned):
        raise ValidationError("Please enter a UK mobile number starting 07", details={"field": "phone"})
    return "+44" + cleaned[1:] if cleaned.startswith("0") else cleaned


def find_by_email(conn, email: str) -> dict | None:
    return db.fetch_one(
        conn,
        "SELECT id, email, full_name FROM residents WHERE email = %s AND deleted_at IS NULL",
        (normalise_email(email),),
    )


def get_resident(conn, resident_id: int) -> dict:
    row = db.fetch_one(
        conn,
        "SELECT id, email, full_name, phone, postcode, is_in_borough, created_at "
        "FROM residents WHERE id = %s AND deleted_at IS NULL",
        (resident_id,),
    )
    if row is None:
        raise NotFound("resident not found")
    row["sms_reminders"] = consents.current(conn, resident_id, "sms_reminders")
    return row


def register(conn, *, email: str, full_name: str, phone: str | None = None,
             postcode: str | None = None, sms_reminders: bool = False) -> int:
    email = normalise_email(email)
    full_name = full_name.strip()
    if not 1 <= len(full_name) <= 120:
        raise ValidationError("Please give your name", details={"field": "full_name"})
    if find_by_email(conn, email) is not None:
        raise ConflictError("There's already an account for that email - just log in")
    row = db.fetch_one(
        conn,
        "INSERT INTO residents (email, full_name, phone, postcode) VALUES (%s, %s, %s, %s) RETURNING id",
        (email, full_name, normalise_phone(phone), (postcode or "").upper().strip() or None),
    )
    # Only write a consent row if they ticked the box. No row = not opted in.
    if sms_reminders:
        consents.record(conn, row["id"], "sms_reminders", True, source="signup_form")
    return row["id"]


def update_profile(conn, resident_id: int, changes: dict) -> dict:
    unknown = set(changes) - set(EDITABLE)
    if unknown:
        # email changes go through the service desk, see docs/accounts/magic-link-login.md
        raise ValidationError(f"can't change: {', '.join(sorted(unknown))}")
    if "phone" in changes:
        changes["phone"] = normalise_phone(changes["phone"])
        # Changing number doesn't touch consents. Opted-in stays opted-in on the new number.
    if "postcode" in changes and changes["postcode"]:
        changes["postcode"] = changes["postcode"].upper().strip()
    for field, value in changes.items():
        conn.execute(f"UPDATE residents SET {field} = %s WHERE id = %s", (value, resident_id))
    return get_resident(conn, resident_id)


def record_consent(conn, resident_id: int, *, purpose: str, granted: bool, source: str) -> None:
    consents.record(conn, resident_id, purpose, granted, source=source)
    if purpose == "sms_reminders" and not granted:
        # stop anything already queued
        conn.execute(
            "UPDATE notifications_outbox SET status = 'failed', last_error = 'consent withdrawn' "
            "WHERE resident_id = %s AND channel = 'sms' AND template = 'booking_reminder' "
            "AND status = 'pending'",
            (resident_id,),
        )
