---
kind: doc
status: verified
---

# Bookings: how the pieces fit

Last properly reviewed: Nov 2025 (GO). If something here disagrees with the
code, the code wins; please fix the doc.

## Where things live

| Module | What it does |
|---|---|
| `hallpass/bookings/slots.py` | The 30-minute local-time grid, validation of a requested window |
| `hallpass/bookings/availability.py` | Free-slot search for the public pages and the staff diary |
| `hallpass/bookings/lifecycle.py` | hold / book on account / confirm / cancel / no-show |
| `hallpass/bookings/recurring.py` | Block bookings ("series"): create, cancel, extend |
| `hallpass/bookings/waitlist.py` | Join, withdraw, offer freed slots |
| `hallpass/bookings/blackouts.py` | Closures and maintenance windows |
| `hallpass/bookings/day_sheet.py` | The caretaker's printout / staff day view |
| `hallpass/bookings/jobs.py` | What the worker runs on a timer |

HTTP handlers are `hallpass/api/bookings.py` (residents, org admins) and
`hallpass/api/staff.py`. They're thin: parse, call one function here, return
JSON. The worker (`hallpass/worker.py`) calls `jobs.release_expired_holds`
every minute, `jobs.sweep_waitlist` every 5 minutes and `jobs.expire_waitlist`
hourly.

## Statuses

A booking (row in `bookings`) is always one of:

- **held** — slot reserved while a resident pays on Paybridge. Has
  `hold_expires_at`. Blocks the slot.
- **confirmed** — paid, or on account for an organisation that pays by
  invoice. Blocks the slot.
- **cancelled** — withdrawn by the hirer, by staff, by a closure, or because
  the hold ran out. `cancel_reason` says which (`customer`, `staff`,
  `closure`, `hold_expired` -- staff can also type their own, which billing
  treats like `staff`). Doesn't block.
- **no_show** — staff marked that nobody turned up. Doesn't block (it's in the
  past anyway). No refund.

Allowed moves: held→confirmed, held→cancelled, confirmed→cancelled,
confirmed→no_show, and the special cancelled(hold_expired)→confirmed when a
payment lands late and the slot is still free.

## Who can book what

- Residents: one-off bookings up to 4 hours, card payment, must be at least
  2 hours ahead.
- Organisations: one-off or series, any length. Orgs with
  `organisations.on_account` are invoiced monthly; the rest pay by card like
  residents. Only an org's *admins* (organisation_members.role = 'admin') can
  book for it -- checked in the API handler, not in bookings (TODO).
- Staff: anything, including past-midnight hires and series for individual
  residents. Staff bookings skip the 2-hour lead time.

## Double bookings

Can't happen for active bookings — the `bookings_no_overlap` exclusion
constraint (ADR 0009) refuses the insert. Closures are a separate table and
are checked in code, so a booking *can* end up inside a blackout if the
blackout was created a split second after the check (HP-611, theoretical).
Creating a closure over existing bookings is refused unless staff tick
"cancel affected bookings"; see `how-to-close-a-space.md`.

## Times

UTC in the database; Europe/London for anything a human sees or picks. Slot
boundaries are local. See `time-and-dst.md` — and the known issue about series
across clock changes, which is the one that keeps biting.
