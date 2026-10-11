---
kind: decision
status: superseded
superseded_by: 0004
date: 2025-02-10
---
# ADR 0002: Store fines as float dollars

## Decision
Store fine amounts as `REAL` dollars (for example `0.25`) and round when
displaying.

## Status
Superseded by ADR 0004 after rounding errors appeared in monthly fine totals.
