"""Who gets a notification, and how. Used by outbox.enqueue.

Rules as they stand (product owner signed off the first three in 2023, the
rest just happened):

1. Email always, to the resident on the booking/series/refund - or to the
   organisation's billing_email when there is no resident (org bookings made
   by staff on the phone).
2. booking_reminder goes by SMS *instead of* email when the resident has a
   phone number and has opted in (consents.sms_reminders) and the caller
   allowed SMS (worker passes the sms_reminders flag through).
3. Never SMS an organisation; we only have an email for them.
4. waitlist_offer and series_sessions_closed ALSO go by SMS to anyone with a
   phone, no consent check - treated as service messages because they're
   time-critical. Not run past IG.
5. Anonymised residents (deleted_at set) get nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hallpass.accounts import consents
from hallpass.core.tz import format_local

ALSO_SMS = {"waitlist_offer", "series_sessions_closed"}

# ref name -> SQL returning (resident_id, booking_id, organisation_id)
_LOOKUPS = {
    "booking_id": "SELECT resident_id, id, organisation_id FROM bookings WHERE id = %s",
    "series_id": "SELECT resident_id, NULL, organisation_id FROM booking_series WHERE id = %s",
    "waitlist_entry_id": "SELECT resident_id, NULL, NULL FROM waitlist_entries WHERE id = %s",
    "refund_id": "SELECT b.resident_id, b.id, b.organisation_id FROM refunds r "
                 "JOIN payments p ON p.id = r.payment_id JOIN bookings b ON b.id = p.booking_id "
                 "WHERE r.id = %s",
    "invoice_id": "SELECT NULL, NULL, organisation_id FROM invoices WHERE id = %s",
    "resident_id": "SELECT id, NULL, NULL FROM residents WHERE id = %s",
}


@dataclass
class Message:
    channel: str
    recipient: str
    resident_id: int | None
    booking_id: int | None
    context: dict = field(default_factory=dict)


def _booking_context(conn, booking_id: int) -> dict:
    row = conn.execute(
        "SELECT b.starts_at, b.ends_at, s.name, f.name FROM bookings b "
        "JOIN spaces s ON s.id = b.space_id JOIN facilities f ON f.id = s.facility_id WHERE b.id = %s",
        (booking_id,),
    ).fetchone()
    starts, ends, space, facility = row
    return {
        "booking_ref": f"HP-B{booking_id}",
        "space_name": space,
        "facility_name": facility,
        "date_text": format_local(starts, "%a %d %b"),
        "time_text": f"{format_local(starts, '%H:%M')}-{format_local(ends, '%H:%M')}",
    }


def resolve(conn, template: str, refs: dict, *, to_email: str | None = None,
            allow_sms: bool = True) -> list[Message]:
    if to_email:
        return [Message("email", to_email, None, None)]
    ref_name = next((k for k in _LOOKUPS if refs.get(k) is not None), None)
    if ref_name is None:
        raise ValueError(f"enqueue({template}) needs one of {sorted(_LOOKUPS)}")
    row = conn.execute(_LOOKUPS[ref_name], (refs[ref_name],)).fetchone()
    if row is None:
        return []
    resident_id, booking_id, org_id = row
    ctx = {k: v for k, v in refs.items() if v is not None}
    if booking_id is not None:
        ctx.update(_booking_context(conn, booking_id))

    if resident_id is None:
        if org_id is None:
            return []
        (billing_email,) = conn.execute(
            "SELECT billing_email FROM organisations WHERE id = %s", (org_id,)
        ).fetchone()
        return [Message("email", billing_email, None, booking_id, ctx)]

    person = conn.execute(
        "SELECT email, full_name, phone FROM residents WHERE id = %s AND deleted_at IS NULL",
        (resident_id,),
    ).fetchone()
    if person is None:
        return []
    email, full_name, phone = person
    ctx["first_name"] = full_name.split()[0] if full_name.strip() else "there"

    if template == "booking_reminder":
        if allow_sms and phone and consents.current(conn, resident_id, "sms_reminders"):
            return [Message("sms", phone, resident_id, booking_id, ctx)]
        if not consents.current(conn, resident_id, "email_reminders"):
            return []
        return [Message("email", email, resident_id, booking_id, ctx)]

    out = [Message("email", email, resident_id, booking_id, ctx)]
    if template in ALSO_SMS and phone:
        out.append(Message("sms", phone, resident_id, booking_id, ctx))
    return out
