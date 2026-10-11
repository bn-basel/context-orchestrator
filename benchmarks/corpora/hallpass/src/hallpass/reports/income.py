"""Income report for finance.

Income is recognised on the *date of the booking* (local), not the date the
money arrived. Finance asked for this in the Jan 2024 reporting meeting so that
block bookings paid upfront spread across the months they're used. Card
payments and invoice payments are both included; refunds are netted off in the
month of the booking they relate to, not the month they were issued. This is
NOT what the Paybridge settlement report shows, so the two will never match
month to month. That's expected - see docs/meetings/2024-01-23-reporting.md.

Everything is pence until the very last moment; formatting is the caller's job.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from hallpass.core import db, money, tz

_INCOME_SQL = """
WITH booking_money AS (
    SELECT
        b.id                                                        AS booking_id,
        s.facility_id,
        (b.starts_at AT TIME ZONE 'Europe/London')::date            AS local_day,
        coalesce(sum(p.amount_pence) FILTER (WHERE p.status IN ('succeeded', 'refunded', 'partially_refunded')), 0) AS paid_pence,
        coalesce((
            SELECT sum(r.amount_pence)
            FROM refunds r
            JOIN payments p2 ON p2.id = r.payment_id
            WHERE p2.booking_id = b.id AND r.status = 'succeeded'
        ), 0)                                                       AS refunded_pence
    FROM bookings b
    JOIN spaces s ON s.id = b.space_id
    LEFT JOIN payments p ON p.booking_id = b.id
    WHERE b.starts_at >= %(start)s AND b.starts_at < %(end)s
    GROUP BY b.id, s.facility_id, local_day
),
invoice_money AS (
    -- Org bookings paid by invoice: take the invoice line amount for the
    -- booking, counted once the invoice is paid.
    SELECT
        il.booking_id,
        s.facility_id,
        (b.starts_at AT TIME ZONE 'Europe/London')::date AS local_day,
        il.gross_pence AS paid_pence
    FROM invoice_lines il
    JOIN invoices i ON i.id = il.invoice_id AND i.status = 'paid'
    JOIN bookings b ON b.id = il.booking_id
    JOIN spaces s ON s.id = b.space_id
    WHERE b.starts_at >= %(start)s AND b.starts_at < %(end)s
)
SELECT
    f.id   AS facility_id,
    f.name AS facility_name,
    coalesce(sum(bm.paid_pence), 0)      AS card_pence,
    coalesce(sum(bm.refunded_pence), 0)  AS refunded_pence,
    coalesce((SELECT sum(im.paid_pence) FROM invoice_money im WHERE im.facility_id = f.id), 0) AS invoice_pence
FROM facilities f
LEFT JOIN booking_money bm ON bm.facility_id = f.id
GROUP BY f.id, f.name
ORDER BY f.name
"""


def income_by_facility(conn, *, start: date, end: date) -> list[dict[str, Any]]:
    range_start, _ = tz.local_day_bounds(start)
    _, range_end = tz.local_day_bounds(end)
    rows = db.fetch_all(conn, _INCOME_SQL, {"start": range_start, "end": range_end})
    out = []
    for r in rows:
        net = int(r["card_pence"]) + int(r["invoice_pence"]) - int(r["refunded_pence"])
        out.append(
            {
                "facility_id": r["facility_id"],
                "facility_name": r["facility_name"],
                "card_pence": int(r["card_pence"]),
                "invoice_pence": int(r["invoice_pence"]),
                "refunded_pence": int(r["refunded_pence"]),
                "net_pence": net,
                # VAT split is indicative only. Charity hires may be exempt
                # (billing are checking with finance), this assumes all standard rated.
                "vat_pence": money.vat_from_gross(net),
                "net_display": money.format_gbp(net),
            }
        )
    return out


def outstanding_invoices(conn, *, as_of: date) -> list[dict[str, Any]]:
    return db.fetch_all(
        conn,
        """
        SELECT i.id, i.number, o.name AS organisation, i.total_pence, i.issued_on, i.due_on,
               i.total_pence - coalesce(sum(p.amount_pence) FILTER (WHERE p.status = 'succeeded'), 0) AS outstanding_pence
        FROM invoices i
        JOIN organisations o ON o.id = i.organisation_id
        LEFT JOIN payments p ON p.invoice_id = i.id
        WHERE i.status = 'issued' AND i.issued_on <= %(as_of)s
        GROUP BY i.id, o.name
        HAVING i.total_pence - coalesce(sum(p.amount_pence) FILTER (WHERE p.status = 'succeeded'), 0) > 0
        ORDER BY i.due_on
        """,
        {"as_of": as_of},
    )
