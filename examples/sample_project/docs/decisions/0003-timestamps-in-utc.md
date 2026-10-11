---
kind: decision
status: verified
date: 2025-02-12
---
# ADR 0003: Store timestamps in UTC

## Decision
All timestamps are stored as ISO-8601 UTC strings (`2025-03-01T14:00:00Z`).
Conversion to the library's local time zone happens only in the presentation
layer. Due dates are stored as UTC timestamps at the end of the due day.

## Consequences
Date arithmetic in `loans.py` must work on UTC values. Code that needs a
calendar day must convert to local time explicitly.
