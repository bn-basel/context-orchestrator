"""Back office endpoints for facility staff, finance and superusers.

Role checks go through hallpass.accounts.roles.require_role. Staff role names
are facility_staff, finance, superuser. (Org admin is a resident-side thing and
never appears here.)
"""

from __future__ import annotations

from datetime import date

from flask import Blueprint, jsonify, request

from hallpass.accounts.roles import require_role
from hallpass.api._helpers import json_body, parse_date, parse_instant, require_staff, to_json
from hallpass.billing import invoices, refunds
from hallpass.bookings import blackouts, lifecycle, recurring
from hallpass.core import clock, db, flags

bp = Blueprint("staff", __name__)


@bp.post("/bookings/<int:booking_id>/no-show")
def mark_no_show(booking_id: int):
    who = require_role(require_staff(), "facility_staff", "superuser")
    if not flags.is_enabled("no_show_tracking"):
        return jsonify({"error": "disabled", "message": "no-show tracking is switched off"}), 404
    with db.transaction() as conn:
        booking = lifecycle.mark_no_show(conn, booking_id, staff_id=who.id)
    return to_json(booking)


@bp.post("/bookings/<int:booking_id>/cancel")
def staff_cancel(booking_id: int):
    who = require_role(require_staff(), "facility_staff", "superuser")
    body = json_body()
    with db.transaction() as conn:
        booking = lifecycle.cancel(conn, booking_id, reason=body.get("reason", "staff"), by_staff_id=who.id)
    return to_json(booking)


@bp.post("/series/<int:series_id>/extend")
def extend_series(series_id: int):
    who = require_role(require_staff(), "facility_staff", "superuser")
    body = json_body()
    with db.transaction() as conn:
        result = recurring.extend_series(
            conn, series_id, parse_date(body.get("new_last_date"), "new_last_date"), staff_id=who.id
        )
    return to_json(result)


@bp.get("/facilities/<int:facility_id>/closures")
def upcoming_closures(facility_id: int):
    require_role(require_staff(), "facility_staff", "finance", "superuser")
    with db.connection() as conn:
        return to_json(blackouts.list_upcoming(conn, facility_id))


@bp.post("/blackouts")
def create_blackout():
    who = require_role(require_staff(), "facility_staff", "superuser")
    body = json_body()
    with db.transaction() as conn:
        result = blackouts.create_blackout(
            conn,
            facility_id=int(body["facility_id"]),
            space_id=body.get("space_id"),
            starts_at=parse_instant(body.get("starts_at"), "starts_at"),
            ends_at=parse_instant(body.get("ends_at"), "ends_at"),
            reason=body["reason"],
            note=body.get("note", ""),
            staff_id=who.id,
            cancel_affected=bool(body.get("cancel_affected", False)),
        )
    # Without cancel_affected, clashing bookings come back as a 409 listing
    # them, and staff decide what to do. We don't auto-cancel by default.
    return to_json(result, 201)


@bp.delete("/blackouts/<int:blackout_id>")
def withdraw_blackout(blackout_id: int):
    who = require_role(require_staff(), "facility_staff", "superuser")
    with db.transaction() as conn:
        blackouts.withdraw_blackout(conn, blackout_id, staff_id=who.id)
    return jsonify({"withdrawn": True})


@bp.post("/refunds")
def manual_refund():
    who = require_role(require_staff(), "finance", "superuser")
    body = json_body()
    with db.transaction() as conn:
        refund_id = refunds.staff_refund(
            conn,
            payment_id=int(body["payment_id"]),
            amount_pence=int(body["amount_pence"]),
            reason=body["reason"],
            staff_id=who.id,
        )
    return jsonify({"refund_id": refund_id}), 201


@bp.post("/invoices/run")
def run_invoices():
    """Manual trigger; normally the worker does this on the 1st. Opens its
    own transactions (one per organisation)."""
    require_role(require_staff(), "finance", "superuser")
    body = request.get_json(silent=True) or {}
    today = clock.today_local()
    month = parse_date(body["month"], "month") if body.get("month") else _previous_month(today)
    created = invoices.run_monthly_invoicing(month, today)
    return jsonify({"created": created})


@bp.post("/invoices/<int:invoice_id>/bank-payment")
def record_bank_payment(invoice_id: int):
    who = require_role(require_staff(), "finance", "superuser")
    body = json_body()
    with db.transaction() as conn:
        payment_id = invoices.record_bank_payment(
            conn,
            invoice_id=invoice_id,
            amount_pence=int(body["amount_pence"]),
            bank_reference=body.get("bank_reference", ""),
            staff_id=who.id,
        )
    return jsonify({"payment_id": payment_id}), 201


@bp.post("/invoices/<int:invoice_id>/void")
def void_invoice(invoice_id: int):
    who = require_role(require_staff(), "finance", "superuser")
    body = json_body()
    with db.transaction() as conn:
        invoices.void_invoice(conn, invoice_id=invoice_id, reason=body["reason"], staff_id=who.id)
    return jsonify({"voided": True})


@bp.put("/flags/<key>")
def toggle_flag(key: str):
    who = require_role(require_staff(), "superuser")
    body = json_body()
    with db.transaction() as conn:
        flags.set_flag(conn, key, bool(body["enabled"]), staff_id=who.id)
    return jsonify({"key": key, "enabled": bool(body["enabled"])})


def _previous_month(today: date) -> date:
    first = today.replace(day=1)
    return (first.replace(year=first.year - 1, month=12) if first.month == 1
            else first.replace(month=first.month - 1))
