"""Database access: a psycopg 3 pool and a few helpers.

We write SQL by hand (ADR 0001). The helpers here exist so call sites don't
have to repeat cursor boilerplate; they are not a query builder and should not
become one.

Usage::

    from hallpass.core import db

    with db.transaction() as conn:
        row = db.fetch_one(conn, "SELECT * FROM spaces WHERE id = %(id)s", {"id": space_id})

Also runnable as ``python -m hallpass.core.db migrate``.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from hallpass.core.config import get_settings
from hallpass.core.errors import ConflictError

log = logging.getLogger(__name__)

_pool: ConnectionPool | None = None

# psycopg surfaces exclusion violations as this SQLSTATE
EXCLUSION_VIOLATION = "23P01"
UNIQUE_VIOLATION = "23505"

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "db" / "migrations"


def _configure(conn: psycopg.Connection) -> None:
    # Session time zone is UTC regardless of the server default. Local-time
    # conversion happens in Python (hallpass.core.tz), never in SQL, except
    # in reports where we use AT TIME ZONE 'Europe/London' explicitly.
    conn.execute("SET TIME ZONE 'UTC'")
    conn.execute("SET statement_timeout = '15s'")
    conn.commit()


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        s = get_settings()
        _pool = ConnectionPool(
            s.database_url,
            min_size=s.db_pool_min,
            max_size=s.db_pool_max,
            kwargs={"row_factory": dict_row},
            configure=_configure,
            open=True,
        )
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def connection() -> Iterator[psycopg.Connection]:
    with pool().connection() as conn:
        yield conn


@contextmanager
def transaction(conn: psycopg.Connection | None = None) -> Iterator[psycopg.Connection]:
    """A connection with an open transaction, committed on clean exit.

    With no argument: borrows a pooled connection (request handlers).
    With a connection: opens a transaction on it, which psycopg turns into a
    savepoint if one is already open (worker jobs that commit per batch).

    Translates the double-booking exclusion violation into ConflictError so
    handlers can return 409 without knowing about SQLSTATEs. Domain code may
    catch ExclusionViolation itself first to raise something more specific.
    """
    if conn is not None:
        try:
            with conn.transaction():
                yield conn
        except psycopg.errors.ExclusionViolation as exc:
            raise ConflictError("That slot has just been taken.", code="slot_taken") from exc
        return
    with pool().connection() as pooled:
        try:
            with pooled.transaction():
                yield pooled
        except psycopg.errors.ExclusionViolation as exc:
            raise ConflictError("That slot has just been taken.", code="slot_taken") from exc


def fetch_one(conn: psycopg.Connection, sql: str, params: Mapping[str, Any] | Sequence[Any] | None = None) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def fetch_all(conn: psycopg.Connection, sql: str, params: Mapping[str, Any] | Sequence[Any] | None = None) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def execute(conn: psycopg.Connection, sql: str, params: Mapping[str, Any] | Sequence[Any] | None = None) -> int:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.rowcount


@contextmanager
def advisory_lock(conn: psycopg.Connection, key: int) -> Iterator[bool]:
    """Session-level try-lock. Yields False if someone else holds it.

    Used by the worker so two cron invocations of the same job don't overlap.
    """
    got = fetch_one(conn, "SELECT pg_try_advisory_lock(%s) AS ok", (key,))
    ok = bool(got and got["ok"])
    try:
        yield ok
    finally:
        if ok:
            conn.execute("SELECT pg_advisory_unlock(%s)", (key,))


# --- migrations -----------------------------------------------------------
# Deliberately dumb: apply every db/migrations/NNNN_*.sql not yet recorded in
# schema_migrations, in filename order, one transaction each. Each file has
# its own BEGIN/COMMIT too, which is harmless inside psycopg's autocommit off.
# No down migrations. Write a new forward one.


def migrate(dry_run: bool = False) -> list[str]:
    applied: list[str] = []
    with psycopg.connect(get_settings().database_url, autocommit=True) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename   text PRIMARY KEY,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        done = {r[0] for r in conn.execute("SELECT filename FROM schema_migrations").fetchall()}
        for path in sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql")):
            if path.name in done:
                continue
            log.info("applying %s", path.name)
            applied.append(path.name)
            if dry_run:
                continue
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (path.name,))
    return applied


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) >= 2 and sys.argv[1] == "migrate":
        names = migrate(dry_run="--dry-run" in sys.argv)
        print("\n".join(names) or "nothing to apply")
    else:
        print("usage: python -m hallpass.core.db migrate [--dry-run]", file=sys.stderr)
        sys.exit(2)
