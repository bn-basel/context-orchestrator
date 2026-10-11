---
kind: decision
status: verified
date: 2025-02-03
---
# ADR 0001: Use SQLite for persistence

## Context
The library runs Shelfwise on a single desk computer. There is no operations
team and no always-on server.

## Decision
Store all data in one SQLite database file (`shelfwise.db`). Access it through
the standard library `sqlite3` module; do not add an ORM.

## Consequences
Backups are a file copy. Only one writer at a time is supported, which is fine
for a single desk. Schema changes are plain SQL migration files in `db/`.
