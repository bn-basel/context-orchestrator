---
kind: decision
status: verified
---

# ADR 0009: Prevent double booking with a Postgres exclusion constraint

- Date: 2023-08-22
- Status: accepted (verified in production since go-live)
- Author: Tom Whitfield

## Context

Two residents clicking "book" on the same slot at the same moment must not
both get it. The first prototype checked availability with a SELECT and then
INSERTed, which is a classic race: in the August 2023 staff pilot at Eastfield we got two
confirmed bookings for Eastfield Court 2 on the same Saturday morning.

Options considered:

1. `SELECT ... FOR UPDATE` on the space row before checking and inserting.
   Serialises all bookings for a space. Works, but every code path has to
   remember to take the lock (series creation, staff screens, waitlist,
   imports...).
2. SERIALIZABLE isolation for booking transactions. Retries everywhere, and
   the error is a generic serialization failure that's hard to turn into a
   helpful message.
3. An exclusion constraint on `bookings` so the database itself refuses
   overlapping active bookings for the same space.

## Decision

Option 3:

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE bookings
  ADD CONSTRAINT bookings_no_overlap
  EXCLUDE USING gist (
    space_id WITH =,
    tstzrange(starts_at, ends_at, '[)') WITH &&
  )
  WHERE (status IN ('held', 'confirmed'));
```

Application code just inserts. If the constraint fires we get
`psycopg.errors.ExclusionViolation` (SQLSTATE 23P01) and turn it into
`BookingConflict`, which the API returns as HTTP 409 with "that time is no
longer available".

## Consequences

- Half-open ranges (`[)`) mean back-to-back bookings (18:00–19:00 then
  19:00–20:00) are allowed. That's what we want.
- **Held bookings count.** A hold blocks the slot exactly like a confirmed
  booking until it's cancelled or expires.
- Cancelled and no-show rows are outside the `WHERE`, so they don't block.
  If a new active-type status is ever added, the constraint's `WHERE` must be
  updated with it (there is a comment in `bookings/models.py`).
- The constraint does **not** know about `blackout_periods`. Closures are
  checked in application code. There is a small window between check and
  insert; we accept it because closures are created rarely and by staff.
- The GiST index the constraint creates also speeds up range overlap
  queries in availability search.
- Inside a larger transaction (series creation) each insert is wrapped in a
  savepoint so one clash doesn't abort the whole transaction.
