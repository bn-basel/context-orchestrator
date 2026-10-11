"""Report downloads for service managers and finance."""

from __future__ import annotations

from flask import Blueprint, Response, request

from hallpass.accounts.roles import require_role
from hallpass.api._helpers import int_arg, parse_date, require_staff, to_json
from hallpass.core import db
from hallpass.reports import export, income, usage

bp = Blueprint("reports", __name__)


def _respond(rows, name: str, start, end):
    if request.args.get("format") == "csv":
        return Response(
            export.to_csv(rows),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={name}_{start}_{end}.csv"},
        )
    return to_json(rows)


@bp.get("/usage")
def usage_report():
    require_role(require_staff(), "facility_staff", "finance", "superuser")
    start = parse_date(request.args.get("from"), "from")
    end = parse_date(request.args.get("to"), "to")
    with db.connection() as conn:
        rows = usage.space_utilisation(conn, start=start, end=end, facility_id=int_arg("facility_id"))
    return _respond(rows, "usage", start, end)


@bp.get("/peak-hours")
def peak_hours_report():
    require_role(require_staff(), "facility_staff", "superuser")
    start = parse_date(request.args.get("from"), "from")
    end = parse_date(request.args.get("to"), "to")
    with db.connection() as conn:
        rows = usage.peak_hours(conn, start=start, end=end, facility_id=int(request.args["facility_id"]))
    return _respond(rows, "peak_hours", start, end)


@bp.get("/income")
def income_report():
    require_role(require_staff(), "finance", "superuser")
    start = parse_date(request.args.get("from"), "from")
    end = parse_date(request.args.get("to"), "to")
    with db.connection() as conn:
        rows = income.income_by_facility(conn, start=start, end=end)
    return _respond(rows, "income", start, end)


@bp.get("/outstanding-invoices")
def outstanding_invoices_report():
    require_role(require_staff(), "finance", "superuser")
    as_of = parse_date(request.args.get("as_of"), "as_of")
    with db.connection() as conn:
        rows = income.outstanding_invoices(conn, as_of=as_of)
    return _respond(rows, "outstanding", as_of, as_of)
