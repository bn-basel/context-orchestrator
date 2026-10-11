---
kind: doc
status: verified
---

# How to set up a block booking (series)

For the bookings officer and anyone covering for them. Updated Oct 2025.

A "block booking" is what the code calls a **series**: the same space, same
weekday, same time, every week (or every 2/3/4 weeks) between two dates. Each
week becomes its own booking, so you can cancel single weeks later.

## From the staff screen

Staff → Block bookings → New.

- **Hirer**: normally an organisation. Individual residents only for things
  like regular music lessons — that's allowed from the staff screen only.
- **Space, weekday, start time, length**: start time on the hour or half hour.
- **From / to**: the season, e.g. first Tuesday in September to the last
  Tuesday before the summer holidays.
- **Every**: 1 week unless they've said otherwise.
- **Skip dates**: bank holidays, half-term if the club doesn't run then. You
  can add more later by cancelling individual weeks.
- **If some weeks clash**: tick "Skip clashing weeks" to create the rest and
  get a list of the clashes. Leave it unticked to reject the whole thing (this
  is what clubs get on the self-service portal).

Max 52 weeks. If a club really wants longer, ask a developer, there's an
override.

Weeks that fall in a closure (e.g. polling day) are left out automatically and
appear under "Skipped — closed" on the confirmation screen. The club is **not**
given an extra week at the end. See blackouts-and-series.md if they ask why.

## ⚠ Series that cross the clock change

There's a bug (HP-503): if a series runs over the last Sunday in October or
the last Sunday in March, the weeks after the change come out **an hour
wrong** (19:00 becomes 18:00 in winter; a winter-started series moves to 20:00
after March).

Until it's fixed, **split the series at the clock change**:

| Season example | Create as |
|---|---|
| Tue 19:00, 2 Sep 2025 – 7 Jul 2026 | (1) 2 Sep – 21 Oct 2025, (2) 28 Oct 2025 – 24 Mar 2026, (3) 31 Mar – 7 Jul 2026 |

All three at 19:00. Put the same note on each ("Thornbury BC 25/26 part 1/3")
so finance can see they're one deal. The invoice is per booking anyway, so it
makes no difference to what the club pays.

After creating, open the diary for the first week after each change and check
the time looks right. Takes a minute and saves a phone call from an angry
treasurer.

## Renewing for next season

"Extend" on an existing series adds weeks up to a new end date. **Don't use
Extend across a clock change** for the same reason as above — create a new
series instead. (Extend also refuses legacy series that start at :15 or :45;
re-create those on the half hour, see ADR 0011. And Extend doesn't work at all
for a series made for an individual resident -- HP-622 -- make a new one.)

## Cancelling

- One week: open the booking in the diary → Cancel.
- The rest of the season: Block bookings → the series → "Cancel remaining".
  Past weeks are left alone. Pick the right reason — "Customer request" gets
  the tiered refund, "Council cancellation" gets everything back. The club
  gets one "block booking cancelled" email, not one per week.
