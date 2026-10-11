---
kind: finding
status: verified
---

# Audit: block bookings shifted by the clock change (HP-503)

Done after the 29 March 2026 change, written up 3 April 2026. G. Owusu, with
Sue Brannigan (bookings officer) checking the club side.

## Question

How many series currently have occurrences at the wrong local time because of
HP-503, and how many clubs actually turned up at the wrong time?

## Method

For every series with active (held or confirmed) occurrences between
1 Sept 2025 and 31 Aug 2026, compared each occurrence's local start time
(`starts_at AT TIME ZONE 'Europe/London'`) with `booking_series.local_start_time`.

```sql
SELECT s.id, s.organisation_id, s.local_start_time,
       (b.starts_at AT TIME ZONE 'Europe/London')::time AS actual_local,
       count(*) AS n
FROM booking_series s
JOIN bookings b ON b.series_id = s.id AND b.status IN ('confirmed', 'held')
WHERE b.starts_at >= '2025-09-01' AND b.starts_at < '2026-09-01'
GROUP BY 1, 2, 3, 4
HAVING (b.starts_at AT TIME ZONE 'Europe/London')::time <> s.local_start_time;
```

## Findings

- 311 active series in the period. **23** had wrong-time occurrences after the
  October 2025 change; 19 of those also after the March 2026 change (the
  other 4 had ended). Plus **6** series started in winter that went an hour
  late after March.
- 412 individual occurrences affected in total (29 series).
- 17 of the 23 October cases were series created **before** the split-series
  workaround was written down (Oct 2025). The other 6 were made by covering
  staff who didn't know about it.
- 4 of the 29 were via `extend_series` (renewals).
- Clubs that reported turning up at the wrong time, or finding another group
  in the hall: 5 (Riverside FC juniors twice). Others had noticed the email
  time and phoned in, or just came at their usual time and the hall happened
  to be free.
- 2 cases where the shifted occurrence blocked a genuine one-off booking at
  the "wrong" hour, so a resident was refused a slot that was really free.

## What we did

- Sue cancelled and re-created the wrong occurrences for all 29 series by
  hand (single bookings at the right time, still linked by a note, not by
  `series_id` — so these clubs' series look shorter than they are in reports).
- Added a reminder to the bookings officer's calendar for the Monday after
  each clock change.

## Conclusion

The workaround works when it's followed and fails when cover staff don't know
about it. This is enough of a problem to justify ADR 0013, or at least the
quick fix on local dates for *new* series. Recommended doing the quick fix
before September 2026 registrations regardless. (As of writing, not
scheduled.)
