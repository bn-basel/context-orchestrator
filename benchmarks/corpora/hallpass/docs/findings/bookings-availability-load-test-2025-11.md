---
kind: finding
status: verified
---

# Load test: availability search (Nov 2025)

Gareth Owusu, 12–14 Nov 2025. Ticket HP-398.

## Why

On 8 and 15 September 2025 (club registration Saturdays) the public facility
pages were timing out between roughly 09:00 and 10:30. Logs showed
`GET /facilities/{id}/availability` p95 above 6 s and DB CPU pinned at 100%.
We had no numbers for what the endpoint could actually take, so we measured.

## Setup

- Staging DB restored from the 1 Nov production backup (anonymised by the
  restore script): ~212k bookings, 140 spaces, 11 facilities.
- Same instance size as production (4 vCPU, 16 GB, Postgres 16.4).
- App: 2 workers × 4 threads, same as production.
- Locust, 7-day search window, facility chosen with production's real mix
  (Northgate 38%, Riverside 21%, rest spread).
- Each run: 2 min ramp, 10 min steady.

## Results — old implementation (query per space per day)

| Target rps | Achieved rps | p50 | p95 | p99 | errors |
|---|---|---|---|---|---|
| 10 | 10 | 180 ms | 410 ms | 690 ms | 0 |
| 25 | 24.6 | 520 ms | 1.8 s | 3.1 s | 0 |
| 50 | 31 | 2.9 s | 7.4 s | 11 s | 4.2% (timeouts) |

Northgate (14 spaces) = 98 queries per request. Each one cheap (~1.5 ms) but
the connection pool (10 per worker) was the bottleneck long before the DB was.

September peak was ~40 rps, which matches the outage.

## Change

Rewrote `availability.search` to do two queries per request (opening hours,
busy ranges as a UNION of bookings and blackouts over the whole window) and
walk the slot grid in Python. No schema changes: the GiST index behind the
exclusion constraint already serves the bookings half of the UNION, and
blackouts are tiny.

## Results — new implementation

| Target rps | Achieved rps | p50 | p95 | p99 | errors |
|---|---|---|---|---|---|
| 10 | 10 | 38 ms | 72 ms | 110 ms | 0 |
| 50 | 50 | 61 ms | 210 ms | 340 ms | 0 |
| 100 | 99.2 | 140 ms | 480 ms | 820 ms | 0 |
| 150 | 118 | 610 ms | 1.9 s | 2.7 s | 0.3% |

Saturates around 120 rps on current hardware, now CPU-bound in Python
(walking the grid for 14 spaces × 7 days). DB CPU stayed under 35%.

## Conclusions

- The N-queries pattern was the cause of the September outages. Fixed.
- Headroom is ~3× last September's peak. Good enough for now.
- Most of the remaining time is Python building slot lists. If we ever need
  more, cache opening hours per process (they change a few times a year) —
  but **don't** cache busy ranges (see availability-search.md, we tried).
- The 28-day staff diary view is ~4× the cost of a 7-day public search. It's
  low-traffic, so leave it.
- Did not test the write path (place_hold) under contention. The exclusion
  constraint should be fine but nobody's measured it. Follow-up: HP-402,
  not started.
