"""audit_log writer.

Call inside the same transaction as the change you're recording, so either
both happen or neither does. The table is append-only (see migration 0006 and
docs/constraints.md); there is deliberately no update/delete helper.
"""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb


def write_audit(
    conn,
    *,
    action: str,
    entity: str,
    entity_id: int | None = None,
    actor_staff_id: int | None = None,
    actor_resident_id: int | None = None,
    detail: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> None:
    """``entity`` is the subject table name, e.g. 'bookings'.

    Actor: staff wins if both are given (superuser impersonating a resident).
    Neither given = 'system' (worker, webhooks).
    """
    if actor_staff_id is not None:
        actor_type, actor_id = "staff", actor_staff_id
    elif actor_resident_id is not None:
        actor_type, actor_id = "resident", actor_resident_id
    else:
        actor_type, actor_id = "system", None

    conn.execute(
        """
        INSERT INTO audit_log (actor_type, actor_id, action, subject_type, subject_id, detail, ip_address)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (actor_type, actor_id, action, entity, entity_id, Jsonb(detail) if detail else None, ip_address),
    )
