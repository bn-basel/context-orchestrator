---
kind: decision
status: verified
---

# 0005 — Materialise recurring bookings as individual rows

Date: 2023-03-07. Authors: Priya Raman, Tom Whitfield.

## Context

About 40% of booked hours are block bookings: clubs that have the same hall
every week for a season. We need to store them somehow. Two obvious options:

1. **Rule only.** Store "Tuesdays 19:00–21:00, Sept–July" in
   `booking_series` and expand it on the fly whenever we compute availability,
   do conflict checks, produce invoices, etc.
2. **Materialise.** Store the rule in `booking_series` *and* insert one
   `bookings` row per occurrence with `series_id` pointing back.

## Decision

Option 2. Every occurrence is a normal row in `bookings`.

## Why

- The double-booking guard (whatever we pick — see 0009) only has to know
  about one table. With rule-only we'd need to expand rules inside the
  conflict check, which can't be done in a constraint.
- Cancelling a single week ("we've got a tournament away on the 14th") is
  just cancelling one row. With rule-only you need an exceptions list.
- Invoicing, no-shows, usage reports, the caretaker's daily sheet all work on
  bookings and don't need to know series exist.
- The volume is small. ~300 active series × ~45 occurrences ≈ 13–14k rows
  a year. Postgres won't notice.

## Downsides we accepted

- Changing a series (new time, different hall) means updating or replacing
  many rows. We decided that's a staff-only operation and it's done as
  "cancel remaining + create new series".
- The rule in `booking_series` and the rows can drift apart if someone edits
  rows by hand. `booking_series` is treated as the record of what was asked
  for, `bookings` as the truth of what's booked.
- Occurrences have to be generated correctly at creation time, including
  across clock changes. (Note added 2025-11 by GO: they aren't — see HP-503
  and ADR 0013.)
