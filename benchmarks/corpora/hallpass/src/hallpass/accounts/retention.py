"""Personal data retention (ADR 0010). Worker job `purge_personal_data`,
Sundays 04:00.

* Financial records (payments, refunds, invoices and the bookings they belong
  to): 6 years from the end of the financial year (31 March). Never touched here.
* Everything else personal: 2 years after the account's last activity.

We anonymise, not delete, residents - bookings and payments reference them.
Contact fields are overwritten and deleted_at is set. Outbox rows older than 2
years are deleted outright; so are memberships of anonymised residents and
superseded consent rows.

audit_log is append-only (the app role can't UPDATE/DELETE it), so old audit
entries that mention a person in `details` stay as they are. IG know.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta

log = logging.getLogger(__name__)

GENERAL_RETENTION = timedelta(days=730)
FINANCIAL_YEARS = 6


def financial_year_end(d: date) -> date:
    return date(d.year if d.month <= 3 else d.year + 1, 3, 31)


def financial_cutoff(today: date) -> date:
    """Financial records from years ending on/before this date may go."""
    return date(financial_year_end(today).year - FINANCIAL_YEARS - 1, 3, 31)


def _candidates(conn, now: datetime) -> list[int]:
    """Inactive 2+ years (no login, no booking starting, no payment) and not
    an org admin of an org with future bookings."""
    cutoff = now - GENERAL_RETENTION
    rows = conn.execute(
        """
        SELECT r.id FROM residents r
        WHERE r.deleted_at IS NULL
          AND coalesce(r.last_login_at, r.created_at) < %(cutoff)s
          AND NOT EXISTS (SELECT 1 FROM bookings b
                          WHERE b.resident_id = r.id AND b.starts_at >= %(cutoff)s)
          AND NOT EXISTS (SELECT 1 FROM payments p JOIN bookings b ON b.id = p.booking_id
                          WHERE b.resident_id = r.id AND p.created_at >= %(cutoff)s)
          AND NOT EXISTS (SELECT 1 FROM organisation_members m
                          JOIN bookings b ON b.organisation_id = m.organisation_id
                          WHERE m.resident_id = r.id AND m.role = 'org_admin'
                            AND b.starts_at > %(now)s)
        ORDER BY r.id LIMIT 5000
        """,
        {"cutoff": cutoff, "now": now},
    ).fetchall()
    return [r[0] for r in rows]


def anonymise_resident(conn, resident_id: int, *, now: datetime, reason: str,
                       actor_staff_id: int | None = None) -> None:
    """Also used by superusers for erasure requests (reason='erasure_request')."""
    conn.execute(
        """
        UPDATE residents
        SET email = 'anon-' || id || '@invalid', full_name = 'Former customer',
            phone = NULL, postcode = NULL, deleted_at = %s
        WHERE id = %s AND deleted_at IS NULL
        """,
        (now, resident_id),
    )
    conn.execute("DELETE FROM organisation_members WHERE resident_id = %s", (resident_id,))
    conn.execute(
        "INSERT INTO audit_log (occurred_at, actor_type, actor_id, action, entity_type, entity_id, details) "
        "VALUES (%s, %s, %s, 'resident.anonymise', 'resident', %s, %s)",
        (now, "staff" if actor_staff_id else "system", actor_staff_id, resident_id,
         json.dumps({"reason": reason})),
    )


def anonymise_expired(conn, *, now: datetime, dry_run: bool = False) -> int:
    ids = _candidates(conn, now)
    if dry_run:
        log.info("retention dry run: would anonymise %s residents", len(ids))
        return len(ids)
    with conn.transaction():
        for rid in ids:
            anonymise_resident(conn, rid, now=now, reason="retention_2y")
        cutoff = now - GENERAL_RETENTION
        conn.execute("DELETE FROM notifications_outbox WHERE created_at < %s", (cutoff,))
        # keep the newest row per resident/purpose - it's the evidence of the current choice
        conn.execute(
            """
            DELETE FROM consents c WHERE c.recorded_at < %s AND EXISTS (
                SELECT 1 FROM consents n WHERE n.resident_id = c.resident_id
                  AND n.purpose = c.purpose AND n.recorded_at > c.recorded_at)
            """,
            (cutoff,),
        )
    # TODO: 6-year financial purge. Nothing is old enough until 31 March 2029.
    return len(ids)
