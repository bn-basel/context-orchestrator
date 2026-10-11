---
kind: known_issue
status: verified
---

# Known issues — bookings & scheduling

Newest first within each section. Ticket numbers are in the HP Jira project.

## Open

### HP-541 — Waitlist offers sent twice / for a slot the person doesn't hold

**Seen:** roughly monthly since mid-2024, mostly Northgate badminton courts.
**Severity:** annoying, no money lost (checkout refuses the slot), a complaint
or two each time.

Two code paths promote waiting-list entries when a slot frees up:

- inline, in `lifecycle.cancel()` (someone cancels a confirmed booking), and
- `jobs.sweep_waitlist` every 5 minutes, which also looks for anything
  cancelled in the last 10 minutes with someone waiting.

`waitlist._next_candidate()` reads the first `waiting` entry with a plain
SELECT — no `FOR UPDATE`, no `SKIP LOCKED` — and `promote_for_slot()` marks
the entry `offered` and **queues the offer message before** placing the hold.
If both paths run within the same second or so they both pick the same entry E:

1. A marks E `offered`, queues the offer, places the hold, commits.
2. B's UPDATE of E was waiting on A's row lock; it goes through once A
   commits, and B queues a second offer to E.
3. B's `place_hold` hits the exclusion constraint (A's hold). B resets E to
   `waiting` — undoing A's bookkeeping — and moves on to the next entry F:
   marks it offered, queues an offer to F, fails to hold again, resets F.
4. B commits, and its queued messages go out with it.

Outcome: E gets two offer emails/texts (and does hold the slot, but the entry
says `waiting`, so paying doesn't mark it `accepted`, and if E later cancels
they can be offered their own slot back). F gets "a slot has become available"
and then "sorry, not available" at checkout.

Stopping the hold-release job from promoting inline (Jan 2025) halved the rate
but didn't fix it.

**Proposed fix (not done):**
- `SELECT ... FOR UPDATE SKIP LOCKED` in `_next_candidate`;
- take an advisory lock on `space_id` at the top of `promote_for_slot`
  (`core.db.advisory_lock`) so only one promoter per space at a time;
- place the hold *first*, queue the message only after it succeeds;
- or simply drop the inline path and rely on the job (costs up to 5 min of
  latency — Leisure Services said that's acceptable, Sept 2025).

There's a skipped reproduction test in `tests/bookings/test_waitlist.py`.

Note: the inline path also ignores the `waitlist` feature flag (the job checks
it per facility). Doesn't matter in practice, because entries can only be
created where the flag is on... except the API checks the flag without a
facility, so that's not quite true either.

### HP-503 — Recurring series an hour out after the clocks change

**Seen:** every October and March since block bookings shipped (2.0.0);
properly diagnosed Nov 2025.
**Severity:** high in practice — clubs turn up at the wrong time, or two clubs
turn up together.

`recurring.occurrence_windows()` takes the first occurrence, converts it to UTC
correctly, and then adds `n × 7 days` **in UTC**. Across a clock change that
keeps the UTC time, not the local time:

- Series starting in British Summer Time: occurrences after the last Sunday of
  October are **one hour earlier** (19:00 → 18:00) until the end of March.
- Series starting in GMT: occurrences after the last Sunday of March are one
  hour **later** (19:00 → 20:00).

Validation only checks the first occurrence, and the shifted times are still on
the half hour, so nothing complains. Because the shifted rows are real
`bookings` rows, the exclusion constraint protects the *wrong* hour: the
18:00 slot shows as taken and the 19:00 slot as free.

`extend_series()` has the same problem, and it's worse: it always computes from
the series' original first date, so renewing a September series in January
produces winter rows at the summer UTC time.

**Workaround:** split series at the clock changes (see
`docs/bookings/how-to-block-bookings.md`). The bookings officer also checks
the diary the week after each change.

**Fix:** doing the arithmetic on local dates is a few lines (there's a branch,
`hp-503-local-dates`), but extending already-materialised series then gives
inconsistent rows. Waiting on ADR 0013 (store local wall-clock time + zone),
which is still only proposed. Audit of affected series:
`docs/findings/bookings-hp503-dst-series-audit-2026-04.md`.

### HP-611 — Booking can slip into a closure created at the same moment

Blackouts aren't in the exclusion constraint. `_blackout_clash()` is checked
before insert, so a closure created between the check and the insert isn't
seen. Theoretical; never observed. Won't fix unless ADR 0013 work touches it.

### HP-622 — `extend_series` crashes for resident series

Staff-made series for individual residents have `organisation_id = NULL` and
`extend_series` passes it straight to `book_on_account`. Error is an ugly 500.
Workaround: create a new series. Small fix, nobody's picked it up.

### HP-470 — No seasonal opening hours

`opening_hours` is one row per space per weekday, full stop. Pitches have
summer and winter hours, so the grounds team edit them by hand in April and
October. In 2025 Riverside's summer hours went in two weeks late and evening
slots weren't bookable. Changing hours also doesn't look at existing bookings
outside the new hours. Proper fix needs `valid_from`/`valid_to` (schema
change, area D) and a check on save.

### Series vs. closures — not a bug, an undecided question

What should happen to a block booking when a closure removes some of its
weeks? Currently: weeks cancelled and refunded, series not extended. See
`docs/bookings/blackouts-and-series.md`.

## Fixed

- **HP-398** (fixed Nov 2025) — availability search timing out under load
  during September registrations. Rewritten as two queries + Python. See the
  load-test finding.
- **Weekday off-by-one** (fixed 2024, no ticket) — series code used Python's
  `weekday()` (Monday = 0) against the table's ISO weekday (Monday = 1). A
  "Tuesday" series was created on Mondays for about a week before anyone
  noticed.
- **HP-355** (fixed in 2.5.0, June 2024) — late Paybridge payments after hold
  expiry. Hold raised from 10 to 15 minutes and `confirm` now revives the hold
  if the slot is still free.
- **HP-212** (fixed 2024) — series insert aborted the whole transaction on the
  first clash. Each insert now runs in a savepoint.
