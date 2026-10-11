---
kind: decision
status: verified
---

# ADR 0011: 30-minute slot granularity

- Date: 2024-03-12
- Deciders: Hannah Leckie, Gareth Owusu, Janet Okafor
- Supersedes: [ADR 0003](0003-fifteen-minute-slots.md)

## Context

After six months on 15-minute slots (ADR 0003, live since 1.0 in September 2023):

- On phones the availability page was a scroll of 50+ start times per space
  per day. Analytics for Oct 2023 – Feb 2024 showed 61% of public sessions on mobile and
  a high drop-off on the "pick a time" step.
- Fewer than 3% of bookings made through the public site used a :15 or :45
  boundary. Almost all of those were the music rooms.
- Caretakers complained about 15-minute gaps between bookings that nobody could
  use, which also made the sports halls look emptier in the usage report than
  they were.
- The availability query had to examine twice as many slots as it needed to.

## Decision

Move to 30-minute slots, still defined in Europe/London local time. Bookings
must start and end on :00 or :30 local. Minimum booking is one slot (30 min).

Existing bookings on the 15-minute grid are **left as they are**. We don't
rewrite them, because many are block bookings with invoices already raised and
some run until 2027. New bookings, including extensions of old series, must
be on the 30-minute grid.

## Consequences

- `hallpass.bookings.slots.SLOT_MINUTES = 30`. The validation rejects :15/:45.
- Availability search must handle busy periods that aren't aligned to the
  grid (a legacy 18:15–19:15 booking blocks the 18:00, 18:30 and 19:00 slots).
  There's a test for this.
- The DB check moves from `bookings_slot_grid` (:00/:15/:30/:45) to
  `bookings_slot_grid_30`, added NOT VALID in migration 0008 so the old rows
  don't block it. It must never be VALIDATEd.
- Pricing: per-slot rates are now per half hour; billing re-did its price
  rules at the same time.
- Music rooms lost the 15-minute option. Leisure Services accepted this; the
  piano teacher at Moorfield was moved to a staff-made series.
- Extending a legacy series whose start time is on a quarter hour fails
  validation. Staff have to re-create it on the half hour. This came up maybe
  five times in 2024/25 and is documented in the block booking how-to.
