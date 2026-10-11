"""Monthly invoices for organisations on account.

Organisations with ``pays_by_invoice = true`` (approved by Finance: schools,
the big clubs, a few charities) book without paying up front. On the 1st of
each month the worker's ``generate_invoices`` job (behind the
``org_invoicing`` flag) calls ``generate_monthly_invoices`` for the previous
calendar month, in local time:

* one invoice per organisation; one line per confirmed or no-show booking
  that *started* in the month (no-shows are charged in full),
* a "late cancellation" line for bookings cancelled inside the ADR 0012
  window -- the hirer pays price minus what a card customer would get back,
* the block-booking discount for series with 10+ sessions *in that month*,
* no VAT columns: invoice_lines.amount_pence is gross. VAT is split when the
  PDF is rendered (vat.py). See the note there.

Payment is by bank transfer, 30 days. Finance match transfers by hand in the
back office ("Mark as paid") -> ``record_bank_transfer``. No bank feed. There
was going to be one.

Invoice numbers: HP-<financial year>-NNNNNN, e.g. HP-2526-000123 for
something issued in May 2025 or February 2026 (FY 2025/26). MAX()+1 under an advisory
lock, not a sequence -- the sequence got out of step after the 2024 restore
drill and we never went back to it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

import structlog
from psycopg import Connection
from psycopg.rows import dict_row

from hallpass.billing.concessions import BLOCK_DISCOUNT_MIN_OCCURRENCES, BLOCK_DISCOUNT_PERCENT
from hallpass.billing.errors import InvoiceStateError
from hallpass.billing.refunds import decide
from hallpass.billing.vat import split_gross, treatment_for
from hallpass.core import clock, db
from hallpass.core.audit import write_audit
from hallpass.core.money import percent_of
from hallpass.core.tz import format_local, local_day_bounds

log = structlog.get_logger(__name__)

PAYMENT_TERMS_DAYS = 30
INVOICE_LOCK_KEY = 0x48500001  # "HP" + 1. Arbitrary, never change it.


@dataclass(frozen=True, slots=True)
class DraftLine:
    booking_id: int | None
    description: str
    amount_pence: int


def financial_year(d: date) -> int:
    return d.year if d.month >= 4 else d.year - 1


def previous_month(today: date) -> date:
    return (today.replace(day=1) - timedelta(days=1)).replace(day=1)


def month_end(first: date) -> date:
    return (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def _next_number(conn: Connection, issued_on: date) -> str:
    fy = financial_year(issued_on)
    prefix = f"HP-{fy % 100:02d}{(fy + 1) % 100:02d}-"
    row = conn.execute(
        "SELECT max(substring(number from 9)::int) FROM invoices WHERE number LIKE %s",
        (prefix + "%",),
    ).fetchone()
    n = (row[0] or 0) + 1 if row else 1
    return f"{prefix}{n:06d}"


def build_lines(bookings: list[dict]) -> list[DraftLine]:
    """Turn booking rows into invoice lines. Pure; see test_invoices_and_vat.py."""
    in_month: dict[int, int] = {}
    for b in bookings:
        if b["series_id"] is not None and b["status"] != "cancelled":
            in_month[b["series_id"]] = in_month.get(b["series_id"], 0) + 1

    lines: list[DraftLine] = []
    for b in bookings:
        when = format_local(b["starts_at"], "%a %d %b %H:%M")
        if b["status"] == "cancelled":
            decision = decide(b["price_pence"], b["starts_at"], b["cancelled_at"], closure=b["cancel_reason"] == "closure")
            charge = b["price_pence"] - decision.amount_pence
            if charge > 0:
                lines.append(DraftLine(b["id"], f"Late cancellation: {b['space_name']}, {when}", charge))
            continue

        amount = b["price_pence"]
        # Only counts this month's sessions of the series. A 12-week block that
        # straddles two months (say 6 + 6) misses the discount on both
        # invoices. HP-377, parked: "fix when someone complains". One has.
        if b["series_id"] is not None and in_month[b["series_id"]] >= BLOCK_DISCOUNT_MIN_OCCURRENCES:
            amount -= percent_of(amount, BLOCK_DISCOUNT_PERCENT)
        suffix = " (no-show)" if b["status"] == "no_show" else ""
        lines.append(DraftLine(b["id"], f"{b['space_name']}, {when}{suffix}", amount))
    return lines


def invoice_organisation(conn: Connection, organisation_id: int, month: date, issued_at: datetime) -> int | None:
    start, _ = local_day_bounds(month)
    _, end = local_day_bounds(month_end(month))
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT b.id, b.series_id, b.starts_at, b.status, b.price_pence,
                   b.cancelled_at, b.cancel_reason, s.name AS space_name, s.kind AS space_kind
              FROM bookings b JOIN spaces s ON s.id = b.space_id
             WHERE b.organisation_id = %s
               AND b.starts_at >= %s AND b.starts_at < %s
               AND b.status IN ('confirmed', 'no_show', 'cancelled')
               AND NOT EXISTS (
                     SELECT 1 FROM invoice_lines il JOIN invoices i ON i.id = il.invoice_id
                      WHERE il.booking_id = b.id AND i.status <> 'void')
             ORDER BY b.starts_at
            """,
            (organisation_id, start, end),
        )
        bookings = cur.fetchall()
    lines = build_lines(bookings)
    if not lines:
        return None

    issued_on = issued_at.date()
    number = _next_number(conn, issued_on)
    total = sum(x.amount_pence for x in lines)
    row = conn.execute(
        """
        INSERT INTO invoices (organisation_id, number, period_start, period_end,
                              total_pence, status, issued_at, due_at)
        VALUES (%s, %s, %s, %s, %s, 'issued', %s, %s)
        RETURNING id
        """,
        (organisation_id, number, month, month_end(month), total, issued_at, issued_at + timedelta(days=PAYMENT_TERMS_DAYS)),
    ).fetchone()
    assert row is not None
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO invoice_lines (invoice_id, booking_id, description, amount_pence) VALUES (%s, %s, %s, %s)",
            [(row[0], x.booking_id, x.description, x.amount_pence) for x in lines],
        )
    log.info("invoice.issued", invoice_id=row[0], number=number, organisation_id=organisation_id, total_pence=total)
    return row[0]


def generate_monthly_invoices(conn: Connection, *, month: date | str | None = None, staff_id: int | None = None) -> list[int]:
    """Invoice every pays_by_invoice organisation for ``month`` (default: last month).

    Each organisation runs in its own savepoint so one bad org (usually a
    booking with no space name after a space was renamed/merged) doesn't stop
    everyone else's invoice. Re-running is safe: bookings already on a
    non-void invoice are skipped.
    """
    if month is None:
        month = previous_month(clock.today_local())
    elif isinstance(month, str):
        month = date.fromisoformat(month[:7] + "-01")
    issued_at = clock.now()
    created: list[int] = []
    with db.advisory_lock(conn, INVOICE_LOCK_KEY) as got:
        if not got:
            log.warning("invoice.run_already_in_progress")
            return []
        orgs = db.fetch_all(conn, "SELECT id FROM organisations WHERE pays_by_invoice ORDER BY id")
        for org in orgs:
            try:
                with conn.transaction():
                    invoice_id = invoice_organisation(conn, org["id"], month, issued_at)
            except Exception:
                log.exception("invoice.failed", organisation_id=org["id"])
                continue
            if invoice_id is not None:
                created.append(invoice_id)
    if staff_id is not None:
        write_audit(conn, actor_staff_id=staff_id, action="invoice.manual_run", entity="invoices", entity_id=None, detail={"month": month.isoformat(), "created": len(created)})
    return created


def record_bank_transfer(conn: Connection, invoice_id: int, *, amount_pence: int, reference: str, staff_id: int) -> dict:
    """Finance matched a bank transfer to an invoice.

    Part payments are fine (some schools pay in two halves). The invoice goes
    to 'paid' once payments cover total_pence. Overpayments are recorded as-is
    and show up in the exceptions email; there are no credit balances.
    The bank reference goes in the audit log -- payments has nowhere to keep it.
    """
    inv = db.fetch_one(conn, "SELECT id, status, total_pence FROM invoices WHERE id = %s FOR UPDATE", (invoice_id,))
    if inv is None:
        raise InvoiceStateError(f"invoice {invoice_id} not found")
    if inv["status"] in ("void", "paid", "draft"):
        raise InvoiceStateError(f"invoice {invoice_id} is {inv['status']}")
    row = conn.execute(
        "INSERT INTO payments (invoice_id, amount_pence, method, status) VALUES (%s, %s, 'bank_transfer', 'succeeded') RETURNING id",
        (invoice_id, amount_pence),
    ).fetchone()
    assert row is not None
    paid = conn.execute(
        "SELECT COALESCE(sum(amount_pence), 0) FROM payments WHERE invoice_id = %s AND status = 'succeeded'",
        (invoice_id,),
    ).fetchone()
    paid_pence = int(paid[0]) if paid else 0
    status = inv["status"]
    if paid_pence >= inv["total_pence"]:
        conn.execute("UPDATE invoices SET status = 'paid', paid_at = now() WHERE id = %s", (invoice_id,))
        status = "paid"
    write_audit(
        conn,
        actor_staff_id=staff_id,
        action="invoice.payment_recorded",
        entity="invoices",
        entity_id=invoice_id,
        detail={"amount_pence": amount_pence, "bank_reference": reference, "payment_id": row[0]},
    )
    return {"invoice_id": invoice_id, "payment_id": row[0], "paid_pence": paid_pence, "status": status}


def void_invoice(conn: Connection, *, invoice_id: int, reason: str, staff_id: int) -> None:
    """Void an issued, unpaid invoice. Its bookings become invoiceable again
    (the NOT EXISTS above ignores void invoices). Lines are kept for the record."""
    inv = db.fetch_one(conn, "SELECT status FROM invoices WHERE id = %s FOR UPDATE", (invoice_id,))
    if inv is None or inv["status"] != "issued":
        raise InvoiceStateError("only issued, unpaid invoices can be voided")
    conn.execute("UPDATE invoices SET status = 'void' WHERE id = %s", (invoice_id,))
    write_audit(conn, actor_staff_id=staff_id, action="invoice.void", entity="invoices", entity_id=invoice_id, detail={"reason": reason})


def vat_breakdown(conn: Connection, invoice_id: int) -> dict:
    """Net/VAT per line for the PDF. Computed fresh every time -- see vat.py.

    series_occurrences here is the size of the whole series, not "this
    month's share" like the block discount uses. Yes, the two disagree.
    """
    rows = db.fetch_all(
        conn,
        """
        SELECT il.id, il.description, il.amount_pence, s.kind AS space_kind,
               o.kind AS org_kind, o.charity_number,
               (SELECT count(*) FROM bookings b2 WHERE b2.series_id = b.series_id) AS series_size
          FROM invoice_lines il
          JOIN invoices i ON i.id = il.invoice_id
          JOIN organisations o ON o.id = i.organisation_id
          LEFT JOIN bookings b ON b.id = il.booking_id
          LEFT JOIN spaces s ON s.id = b.space_id
         WHERE il.invoice_id = %s
         ORDER BY il.id
        """,
        (invoice_id,),
    )
    out_lines = []
    net = vat = 0
    for r in rows:
        org = {"kind": r["org_kind"], "charity_number": r["charity_number"]}
        t = treatment_for(space_kind=r["space_kind"] or "", organisation=org, series_occurrences=r["series_size"] or 1)
        split = split_gross(r["amount_pence"], t)
        net += split.net_pence
        vat += split.vat_pence
        out_lines.append({"id": r["id"], "description": r["description"], "net_pence": split.net_pence, "vat_pence": split.vat_pence, "gross_pence": split.gross_pence, "vat": t.value})
    return {"lines": out_lines, "net_pence": net, "vat_pence": vat, "gross_pence": net + vat}
