---
kind: decision
status: superseded
---

# ADR 0003: 15-minute slot granularity

- Date: 2023-02-14
- Deciders: Priya Raman, Tom Whitfield, Janet Okafor (Leisure Services bookings lead)
- Superseded by: [ADR 0011](0011-thirty-minute-slots.md) (March 2024)

## Context

The old system (the paper diary at each centre plus the "Bookings.xls" shared
drive spreadsheet) let staff write in any time at all. Music practice rooms
were often booked 17:15–18:00 to fit around school pick-up, and the
grass pitches have 15-minute changeover gaps between junior matches.

We need a fixed grid so that the availability page can show a list of start
times and so prices can be calculated per slot.

## Decision

Bookable time is divided into 15-minute slots in Europe/London local time.
A booking must start and end on a quarter hour. Minimum booking length is
one slot (15 minutes).

## Consequences

- Availability for a 07:00–23:00 day is 64 slots per space. With ~140 spaces
  across the 11 facilities, the "whole facility" view renders a lot of cells,
  but it's fine on desktop.
- Pricing (billing) charges per 15-minute slot; hourly rates are divided by 4.
- Staff can reproduce every existing paper booking, which matters for the
  migration of the 2022/23 season's block bookings.

## Notes

Tom pointed out that most hires are whole hours and the public site will be
a long list of times on a phone. We agreed to revisit after the first season.
