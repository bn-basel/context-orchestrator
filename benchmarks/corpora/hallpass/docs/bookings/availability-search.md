---
kind: doc
status: verified
---

# Availability search — design notes

`hallpass.bookings.availability.search()` answers "which half-hour slots can
I book in these spaces between these dates?". It's the most-called thing in
the system: every visit to a facility page calls it for 7 days × every space
in the building, and the booking API calls it for one space (1–14 days)
each time someone opens the time picker.

## Inputs

- `space_ids` — usually all bookable spaces in a facility
- `first_day`, `last_day` — local dates, inclusive, max 28 days apart
- `min_length` — "I need 2 hours"; only starts that have that much
  contiguous free time come back
- `for_staff` — drops the 2-hour lead time
- `include_held` — return slots occupied by someone else's *hold* flagged as
  `held_by_other` (diary shows them striped; the public site greys them out
  with "someone is booking this — try again in 15 minutes")

## Algorithm (since Nov 2025)

1. One query for opening hours of all requested spaces.
2. One query for everything that makes a space busy in the window: active
   bookings (held + confirmed) UNION blackouts (space-level and
   facility-level). Uses the GiST index from the exclusion constraint for the
   `&&` range test.
3. In Python, for each space and each local day, walk the opening-hours grid
   (`slots.slots_for_day`) and drop slots that overlap anything busy.
4. If `min_length` > 30 min, keep only slot starts that begin a long-enough
   run.

The grid is built in local time and each boundary converted to UTC
separately, which is what makes clock-change days come out right.

### Before Nov 2025

It was one query per space per day, each doing its own join to bookings and
blackouts. For the busiest facility (Northgate, 14 spaces) a 7-day search
was 98 queries. Fine at quiet times, fell over during the September club
registration rush. See the load-test write-up in
`docs/findings/bookings-availability-load-test-2025-11.md`.

## Opening hours

`opening_hours` is one row per space per ISO weekday (1 = Monday, unique on
`(space_id, weekday)`). No row = closed that day. There is no notion of
seasonal hours: the grounds team change the pitch hours by hand in April and
October, and if they're late the pitches show the wrong hours (HP-470).

Careful with weekdays: Python's `date.weekday()` is Monday = 0, the table is
Monday = 1. Use `isoweekday()`. This has bitten us at least twice.

Bank holidays are NOT in opening_hours. They're handled as closures
(blackouts) that the bookings officer enters each January. If she forgets, the
centre shows as open. Has happened.

## Legacy 15-minute bookings

Pre-March-2024 bookings can start/end on :15/:45 (ADR 0011). Because we test
overlaps on real ranges rather than slot indexes, they just block every slot
they touch. No special code.

## Caching

None. We tried a 30-second cache in 2024 and it produced "available" slots
that weren't, which led to 409s at checkout and complaints. The query is fast
enough now.
