"""Reconciliation: Paybridge settlements vs our `payments` / `refunds`.

Written after the March 2025 manual audit
(docs/findings/billing-reconciliation-audit-2025-03.md); the categories
below are the ones that audit turned up. It reports, it never fixes --
every mismatch so far has needed a human.

Run by the worker (``reconcile_paybridge``) and by hand for past days:

    python -m hallpass.billing.reconciliation --day 2025-06-14

Mismatches go into ``reconciliation_exceptions`` (migration 0010) and a
summary is emailed to the finance systems mailbox via the outbox. Finance
mark rows resolved in the back office (resolved_at / resolved_by). They do
this in bursts, about monthly.
"""

from __future__ import annotations

import argparse
import enum
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

import structlog
from psycopg import Connection
from psycopg.types.json import Jsonb

from hallpass.billing.paybridge import PaybridgeClient
from hallpass.core import clock, db
from hallpass.core.config import get_settings
from hallpass.core.tz import local_day_bounds
from hallpass.notifications.outbox import enqueue

log = structlog.get_logger(__name__)

# Differences at or below this are reported as 'penny' and left out of the
# email body (just counted). Left over from the first version, which compared
# Paybridge against a price recomputed from the tariff and drowned in HP-412
# concession pennies. Against payments.amount_pence the amounts should match
# exactly, so a 'penny' row now would actually be odd. Nobody's seen one.
PENNY_TOLERANCE = 2


class Kind(enum.StrEnum):
    MISSING_LOCALLY = "missing_locally"  # Paybridge took money; no succeeded payment here
    MISSING_REMOTELY = "missing_remotely"  # we say succeeded; not in the settlement file
    AMOUNT_MISMATCH = "amount_mismatch"
    PENNY = "penny"
    REFUND_STUCK = "refund_stuck"  # Paybridge settled a refund we still show as requested/submitted
    REFUND_UNKNOWN = "refund_unknown"  # refund in Paybridge we never asked for (dashboard refund)


@dataclass(frozen=True, slots=True)
class Mismatch:
    kind: Kind
    paybridge_id: str
    local_id: int | None
    detail: str


def compare(settled: Iterable[dict], local_payments: list[dict], local_refunds: list[dict]) -> list[Mismatch]:
    """Pure comparison. ``settled`` rows look like Paybridge's settlement
    report: {"type": "payment" | "refund", "id": "pay_..." | "re_...", "amount": int}."""
    out: list[Mismatch] = []
    payments_by_pb = {p["paybridge_payment_id"]: p for p in local_payments if p["paybridge_payment_id"]}
    refunds_by_pb = {r["paybridge_refund_id"]: r for r in local_refunds if r["paybridge_refund_id"]}

    seen: set[str] = set()
    for item in settled:
        pb_id = item["id"]
        seen.add(pb_id)
        if item["type"] == "refund":
            r = refunds_by_pb.get(pb_id)
            if r is None:
                out.append(Mismatch(Kind.REFUND_UNKNOWN, pb_id, None, "refund made outside Hallpass?"))
            elif r["status"] in ("requested", "submitted"):
                out.append(Mismatch(Kind.REFUND_STUCK, pb_id, r["id"], f"settled at Paybridge, '{r['status']}' here"))
            continue

        p = payments_by_pb.get(pb_id)
        if p is None:
            out.append(Mismatch(Kind.MISSING_LOCALLY, pb_id, None, f"{item['amount']}p"))
            continue
        diff = item["amount"] - p["amount_pence"]
        if diff:
            kind = Kind.PENNY if abs(diff) <= PENNY_TOLERANCE else Kind.AMOUNT_MISMATCH
            out.append(Mismatch(kind, pb_id, p["id"], f"paybridge {item['amount']}p vs ours {p['amount_pence']}p"))

    for pb_id, p in payments_by_pb.items():
        if pb_id not in seen:
            out.append(Mismatch(Kind.MISSING_REMOTELY, pb_id, p["id"], "not in settlement file"))
    return out


def reconcile_day(conn: Connection, *, day: date, dry_run: bool = False, client: PaybridgeClient | None = None) -> int:
    """Returns the number of mismatches (pennies included)."""
    client = client or PaybridgeClient()
    settled = client.settlements(day)
    # Paybridge settlement days are UTC midnight-to-midnight; ours are local.
    # In summer an hour of payments lands in the "wrong" day on one side and
    # shows up as missing_remotely one night and missing_locally the next.
    # Known, documented, ignored.
    start, end = local_day_bounds(day)
    local_payments = db.fetch_all(
        conn,
        """
        SELECT id, paybridge_payment_id, amount_pence FROM payments
         WHERE method = 'card' AND status IN ('succeeded', 'refunded', 'partially_refunded')
           AND created_at >= %s AND created_at < %s
        """,
        (start, end),
    )
    local_refunds = db.fetch_all(
        conn,
        "SELECT id, paybridge_refund_id, status FROM refunds WHERE created_at >= %s AND created_at < %s",
        (start, end),
    )
    found = compare(settled, local_payments, local_refunds)
    log.info("reconciliation.done", day=day.isoformat(), mismatches=len(found), settled=len(settled))
    if found and not dry_run:
        _store(conn, day, found)
        _email_finance(conn, day, found)
    return len(found)


def _store(conn: Connection, day: date, found: list[Mismatch]) -> None:
    # ON CONFLICT so a re-run for the same day (e.g. by hand after an outage)
    # doesn't duplicate rows. paybridge_id is '' rather than NULL in that
    # table precisely so the unique constraint works.
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO reconciliation_exceptions (day, kind, paybridge_id, local_id, detail)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (day, kind, paybridge_id) DO NOTHING
            """,
            [(day, m.kind.value, m.paybridge_id or "", m.local_id, Jsonb({"detail": m.detail})) for m in found],
        )


def _email_finance(conn: Connection, day: date, found: list[Mismatch]) -> None:
    serious = [m for m in found if m.kind is not Kind.PENNY]
    mailbox = get_settings().extra.get("FINANCE_MAILBOX", "")
    if not mailbox:
        log.warning("reconciliation.no_finance_mailbox_configured")
        return
    enqueue(
        conn,
        kind="reconciliation_exceptions",
        channel="email",
        recipient=mailbox,
        resident_id=None,
        payload={
            "day": day.isoformat(),
            "penny_count": len(found) - len(serious),
            "items": [{"kind": m.kind.value, "paybridge_id": m.paybridge_id, "local_id": m.local_id, "detail": m.detail} for m in serious],
        },
        clock=clock,
        dedupe_key=f"recon:{day.isoformat()}",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconcile one day of Paybridge settlements")
    parser.add_argument("--day", type=date.fromisoformat, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    with db.transaction() as conn:
        n = reconcile_day(conn, day=args.day, dry_run=args.dry_run)
    print(f"{args.day}: {n} mismatch(es)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
