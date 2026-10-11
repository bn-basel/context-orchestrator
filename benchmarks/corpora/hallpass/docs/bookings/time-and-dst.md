---
kind: convention
status: assumption
---

# Time zones and clock changes in bookings

## The rule

- In the database: `timestamptz`, always written as UTC.
- In anything a person sees or picks: Europe/London.
- Slot boundaries (:00, :30) are checked **in local time**.
- Convert at the edges with `hallpass.core.tz.to_local` / `local_to_utc` /
  `local_day_bounds`. Don't do arithmetic on aware local datetimes, and don't
  add `timedelta(days=7)` to a UTC instant expecting the same local time next
  week.
  (That second one is exactly HP-503.)

## Wall-clock vs elapsed time

Two different things, both used on purpose:

| Question | Which | Where |
|---|---|---|
| Is this booking longer than 4h? | elapsed (UTC difference) | `slots.validate_booking_window` |
| How many slots to charge for? | wall-clock (local difference) | `slots.slot_count` |
| What's the next slot after 09:30? | wall-clock | `slots.slots_for_day` |
| Same time next week? | **should be** wall-clock | `recurring.occurrence_windows` — currently elapsed, bug |

## Assumption: nothing is open overnight on changeover nights

We assume no space is ever open between 01:00 and 02:00 local time on the last
Sunday of March or October, so we never have to deal with:

- the spring gap (01:00–02:00 doesn't exist), or
- the autumn fold (01:00–02:00 happens twice).

This is **not enforced**. `opening_hours` would happily accept 00:00–23:30
for a space, and the Moorfield sleepover is an overnight staff booking.
If either ever lands on a changeover night: in spring, `local_to_utc` raises
`NonExistentLocalTime` and the availability search for that facility errors;
in autumn the grid shows 01:00 and 01:30 once each although two hours of real
time pass. Nobody has checked what pricing does in that case.

(`facilities.timezone` exists and is always 'Europe/London'. Nothing in
bookings reads it; `core.tz.LONDON` is hard-coded.)

ADR 0013 proposes rejecting those times outright.

## Testing

`tests/bookings/test_slots.py` has cases for 26 Oct 2025 and 29 Mar 2026. When
adding date-based tests, prefer those two dates — they've caught real bugs.
