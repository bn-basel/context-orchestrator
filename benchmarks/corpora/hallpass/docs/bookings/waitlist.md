---
kind: doc
status: verified
---

# Waiting list

Residents can join a waiting list for a slot that's fully booked. It's
popular for the badminton courts at Northgate on weekday evenings and the
3G pitch on Saturday mornings, and not used much anywhere else.

It's behind the `waitlist` feature flag, per facility. It was piloted at
Eastfield (2.2.0) and is now on at most centres, but check the flag before
promising it to anyone.

## Rules

- Residents only (organisations don't use it — they have block bookings).
- At most 5 active entries per resident.
- You wait for an exact time range. If you want 19:00–21:00 and someone
  cancels 19:00–20:00, you're not offered it.
- First come, first served (by `created_at`).
- Nothing is offered less than 3 hours before the start. Entries for slots
  that have passed are marked `expired` by the hourly job.

## What happens when a slot frees up

A slot frees up when a booking is cancelled or a hold expires. Then:

1. The first waiting entry whose range fits inside the freed range is picked.
2. Its status goes to `offered`, and an offer message is queued (email, plus
   SMS to anyone with a mobile number -- offers aren't consent-checked, see
   `docs/privacy.md`).
3. A hold is placed in their name with a 2-hour expiry. The message has a
   link straight to checkout.
4. If they pay → booking confirmed, entry `accepted`.
   If not → the hold expires, the entry goes `lapsed`, and step 1 runs again
   for the next person.

Steps 1–3 happen in two places: straight away inside the cancellation, and in
the worker's 5-minute `sweep_waitlist` job, which also handles lapsed offers
and expired holds (the hold-expiry job deliberately doesn't promote).

## Known problem

The two promotion paths can run at once and trip over each other (HP-541).
Typical result: the first person in the queue gets *two* offer emails (and
does have the slot), and the second person gets an offer for a slot that's
actually the first person's — checkout tells them it's unavailable. See
`docs/known-issues/bookings.md` for the mechanics and the proposed fix.

## Table

`waitlist_entries(id, resident_id, space_id, starts_at, ends_at, status,
offer_booking_id, offered_at, created_at, updated_at)`, plus `position`, which
is left over from the first version and no longer used. Partial unique index
on `(resident_id, space_id, starts_at) WHERE status = 'waiting'` so the join
button is idempotent.
