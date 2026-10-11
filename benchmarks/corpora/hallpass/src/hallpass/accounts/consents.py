"""Consent records (`consents` table, migration 0006).

Append-only in spirit: one row per decision, latest row per (resident,
purpose) wins. Gives IG the history they asked for in the DPIA review.

Purposes (CHECK constraint): sms_reminders, email_reminders, marketing, photo.

Defaults when a resident has no row:

    sms_reminders    False  - SMS reminders are opt-in by default
    email_reminders  True   - service message, no consent needed
    marketing        False
    photo            False  - photography at events, paper forms mostly

The sms_reminders default is what the team *believes* the whole system does:
nobody gets a reminder text unless they ticked "Text me reminders". That is
the code path here, but it hasn't been checked end to end - the sign-up form
lives in the frontend repo and nobody has looked at whether its checkbox
starts ticked, and ~4,000 rows with source='import' came over from the old
Access database in 2023 with granted=true where the old "contact me by text"
box was ticked. See docs/notifications/reminders.md.
"""

from __future__ import annotations

from hallpass.core import clock

PURPOSES = ("sms_reminders", "email_reminders", "marketing", "photo")

DEFAULTS = {
    "sms_reminders": False,
    "email_reminders": True,
    "marketing": False,
    "photo": False,
}

# source values in use: signup_form, account_page, staff_phone, import, sms_stop


def current(conn, resident_id: int, purpose: str) -> bool:
    row = conn.execute(
        "SELECT granted FROM consents WHERE resident_id = %s AND purpose = %s "
        "ORDER BY recorded_at DESC, id DESC LIMIT 1",
        (resident_id, purpose),
    ).fetchone()
    return DEFAULTS[purpose] if row is None else bool(row[0])


def record(conn, resident_id: int, purpose: str, granted: bool, *, source: str) -> None:
    if purpose not in PURPOSES:
        raise ValueError(f"unknown consent purpose {purpose!r}")
    conn.execute(
        "INSERT INTO consents (resident_id, purpose, granted, source, recorded_at) "
        "VALUES (%s, %s, %s, %s, %s)",
        (resident_id, purpose, granted, source, clock.now()),
    )


def sms_opted_in(conn, resident_ids: list[int]) -> set[int]:
    """Bulk check for the reminder job: ids whose latest sms_reminders row is
    granted. Residents with no row are not returned (default False)."""
    if not resident_ids:
        return set()
    rows = conn.execute(
        "SELECT DISTINCT ON (resident_id) resident_id, granted FROM consents "
        "WHERE purpose = 'sms_reminders' AND resident_id = ANY(%s) "
        "ORDER BY resident_id, recorded_at DESC, id DESC",
        (resident_ids,),
    ).fetchall()
    return {rid for rid, granted in rows if granted}
