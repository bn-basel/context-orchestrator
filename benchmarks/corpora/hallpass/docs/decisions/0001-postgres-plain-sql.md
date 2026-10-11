---
kind: decision
status: verified
---

# ADR 0001: PostgreSQL with psycopg and plain SQL, no ORM

- Date: 2023-06-08
- Deciders: Tom Ellery, Aisha Okafor, Gareth Hughes (Digital Infrastructure, DBA)

## Context

We're replacing the spreadsheet-plus-phone process (and the old Access
database at Northgate) with a proper booking system. It needs a database the
council's infrastructure team will actually support: they run PostgreSQL and
SQL Server, and only have spare capacity on the Postgres side.

The interesting parts of the data model are things Postgres is good at and
ORMs are bad at expressing: range overlap (two bookings for the same space
must not overlap), partial indexes, `AT TIME ZONE` maths for local-time
reporting, `jsonb` for webhook payloads.

The team is small and rotates. Whatever we pick, the next developer has to be
able to read it without learning an abstraction first. Two of us have had
bad experiences debugging SQLAlchemy session state in the previous project
(the parking permits system).

## Decision

- PostgreSQL (16 at the time of writing; we follow the DBA team's supported
  version).
- psycopg 3 with its built-in connection pool, `dict_row` rows.
- Hand-written SQL in the Python modules that use it, with named parameters.
  Thin helpers in `hallpass.core.db` for fetch/execute/transaction only.
- Schema changes as numbered plain `.sql` migration files applied in order by
  a tiny runner of our own. No Alembic.
- Use database constraints for invariants wherever possible (CHECKs,
  exclusion constraints, unique constraints) rather than relying on
  application checks.

## Consequences

- Good: what runs is what you read. EXPLAIN output maps directly to code.
  The DBA can review queries in PRs.
- Good: invariants like "no double booking" live in the DB (later formalised
  in ADR 0009) and hold even if someone runs SQL by hand.
- Bad: no automatic mapping, so there's some repetitive row-to-dict code.
  Accepted.
- Bad: renaming a column means grepping for it in SQL strings. Keep queries
  as module-level constants to make that tolerable.
- Bad: our migration runner has no down migrations. Recovery from a bad
  migration is a new forward migration or a restore.

## Notes

Revisited informally in 2025 when a contractor suggested SQLModel. Nobody
wanted it. Still verified.
