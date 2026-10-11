---
kind: decision
status: verified
supersedes: 0002
date: 2025-04-01
---
# ADR 0004: Store money as integer cents

## Context
Float dollar amounts (ADR 0002) produced rounding errors when monthly fine
totals were summed.

## Decision
Every monetary amount (fines, replacement costs, payments) is an integer
number of cents in Python and an `INTEGER` column in SQLite. Column names end
in `_cents`. Use the helpers in `shelfwise.money` to parse and format.

## Consequences
No floats anywhere in fine calculations. Division (for example pro-rated
fines) must use integer arithmetic and round half up explicitly.
