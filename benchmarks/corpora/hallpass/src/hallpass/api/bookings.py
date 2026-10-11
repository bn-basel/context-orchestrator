"""Resident-facing booking endpoints.

All the rules (opening hours, booking window, 30-minute grid, holds) live in
hallpass.bookings. If you're tempted to add an `if` here, don't.
"""

from __future__ import annotations

from datetime import timedelta

from flask import Blueprint, request

from hallpass.api._helpers import (
    int_arg,
    json_body,
    parse_date,
    parse_instant,
    parse_time,
    require_resident,
    to_json,
)
from hallpass.billing import refunds
from hallpass.bookings import availability, lifecycle, recurring, waitlist
from hallpass.bookings.models import SeriesSpec
from hallpass.core import db, flags
from hallpass.core.errors import NotFound

bp = Blueprint("bookings", __name__)


@bp.get("/availability")
def get_availability():
    space_id = int_arg("space_id")
    first = parse_date(request.args.get("date"), "date")
    days = min(int_arg("days", 1) or 1, 14)
    min_minutes = int_arg("min_minutes", 30) or 30
    with db.connection() as conn:
        slots = availability.search(
            conn,
            space_ids=[space_id],
            first_day=first,
            last_day=first + timedelta(days=days - 1),
            min_length=timedelta(minutes=min_minutes),
        )
    return to_json({"space_id": space_id, "from": first, "slots": slots})


@bp.post("")
def create_booking():
    """Places a hold. The hold becomes a confirmed booking when payment
    succeeds (Paybridge webhook). Invoice-paying orgs use /org-booking."""
    who = require_resident()
    body = json_body()
    with db.transaction() as conn:
        booking = lifecycle.place_hold(
            conn,
            space_id=int(body["space_id"]),
            starts_at=parse_instant(body.get("starts_at"), "starts_at"),
            ends_at=parse_instant(body.get("ends_at"), "ends_at"),
            resident_id=who.id,
            organisation_id=body.get("organisation_id"),
        )
    return to_json(booking, 201)


@bp.get("/<int:booking_id>")
def get_booking(booking_id: int):
    who = require_resident()
    with db.connection() as conn:
        booking = lifecycle.get_booking(conn, booking_id)
    # 404 rather than 403 so ids can't be probed
    if booking.resident_id != who.id:
        raise NotFound("booking not found")
    return to_json(booking)


@bp.get("/<int:booking_id>/refund-preview")
def refund_preview(booking_id: int):
    """What would I get back if I cancelled now? (ADR 0012 tiers.)"""
    who = require_resident()
    with db.connection() as conn:
        booking = lifecycle.get_booking(conn, booking_id)
    if booking.resident_id != who.id:
        raise NotFound("booking not found")
    return to_json(refunds.refund_preview(booking.price_pence, booking.starts_at))


@bp.post("/<int:booking_id>/cancel")
def cancel(booking_id: int):
    who = require_resident()
    with db.transaction() as conn:
        booking = lifecycle.get_booking(conn, booking_id, for_update=True)
        if booking.resident_id != who.id:
            raise NotFound("booking not found")
        # lifecycle.cancel asks billing for the refund in the same transaction
        booking = lifecycle.cancel(conn, booking_id, reason="customer")
    return to_json(booking)


@bp.post("/series")
def create_series():
    """Block bookings from the org portal. All-or-nothing on clashes."""
    who = require_resident()
    body = json_body()
    spec = SeriesSpec(
        space_id=int(body["space_id"]),
        organisation_id=body.get("organisation_id"),
        resident_id=None if body.get("organisation_id") else who.id,
        weekday=int(body["weekday"]),
        start_time=parse_time(body.get("start_time"), "start_time"),
        duration_minutes=int(body["duration_minutes"]),
        first_date=parse_date(body.get("first_date"), "first_date"),
        last_date=parse_date(body.get("last_date"), "last_date"),
        every_n_weeks=int(body.get("every_n_weeks", 1)),
        notes=body.get("notes", ""),
    )
    # TODO: org admin check belongs in recurring.create_series, it's here
    # because of the 2.0 deadline. accounts.roles.require_org_admin.
    if spec.organisation_id is not None:
        from hallpass.accounts.roles import require_org_admin

        with db.connection() as conn:
            require_org_admin(conn, who, spec.organisation_id)
    with db.transaction() as conn:
        result = recurring.create_series(conn, spec)
    return to_json(result, 201)


@bp.post("/series/<int:series_id>/cancel")
def cancel_series(series_id: int):
    require_resident()
    body = request.get_json(silent=True) or {}
    from_date = parse_date(body["from_date"], "from_date") if body.get("from_date") else None
    with db.transaction() as conn:
        cancelled = recurring.cancel_series(conn, series_id, from_date=from_date, reason="customer")
    return to_json({"cancelled_booking_ids": cancelled})


@bp.post("/waitlist")
def join_waitlist():
    who = require_resident()
    body = json_body()
    space_id = int(body["space_id"])
    if not flags.is_enabled("waitlist", subject=who.id):
        raise NotFound("waitlist is not available yet")
    with db.transaction() as conn:
        entry_id = waitlist.join(
            conn,
            resident_id=who.id,
            space_id=space_id,
            starts_at=parse_instant(body.get("starts_at"), "starts_at"),
            ends_at=parse_instant(body.get("ends_at"), "ends_at"),
        )
    return to_json({"id": entry_id}, 201)


@bp.delete("/waitlist/<int:entry_id>")
def leave_waitlist(entry_id: int):
    who = require_resident()
    with db.transaction() as conn:
        waitlist.withdraw(conn, entry_id, who.id)
    return to_json({"withdrawn": True})
