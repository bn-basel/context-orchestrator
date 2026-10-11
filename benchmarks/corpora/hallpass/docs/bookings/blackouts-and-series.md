---
kind: doc
status: unverified
---

# Blackouts vs block bookings — open question

**Status: undecided.** Raised by Leisure Services (Janet Okafor) in
February 2025, discussed twice since, no decision. This page records what the
system does now and the options on the table. Please don't change the
behaviour without a decision from Leisure Services + finance.

## What happens today

There are two cases, and they behave differently.

**A. Closure already exists when the series is created.** Occurrences that
fall inside it are skipped, listed under "Skipped — closed" on the
confirmation screen, and otherwise only recorded in the `audit_log` detail for
the `series.create` entry. The series
end date is not moved. The club gets, say, 43 weeks instead of 44 and pays for
43.

**B. Closure is added after the series exists.** Staff get the list of
affected bookings and must tick "cancel affected bookings" to go ahead. The
affected occurrences are cancelled with reason `closure` (full refund / credit,
regardless of notice) and the club gets a single "some of your sessions can't
go ahead" message (email, and a text to the contact's mobile) listing the
dates. The series end date is not moved; nobody is offered an alternative
slot.

Things that are a bit odd about this:

- In case A the club never gets a notification about the missing week —
  only whoever created the series sees it on screen. If it was made on the
  self-service portal, the org admin saw it; the treasurer (who gets the
  invoices) didn't.
- In case B the message says which sessions are off but not that the season
  is now shorter, or that nothing will replace them. Clubs read it as "we'll
  sort out new dates" and ring up.
- In case B, if the closure is later withdrawn (e.g. the election is
  cancelled, or the floor contractor finishes early) the cancelled sessions
  are **not** restored. Staff have to rebook by hand, and the refund may
  already have gone out.
- Partial overlaps: a closure from 18:00–20:00 against a 19:00–21:00 session
  cancels the whole session. Clubs have asked whether they could keep 20:00–21:00.
  We'd need to split the booking, which nothing does yet.

## Options discussed

1. **Leave it** (current). Simple. Clubs complain about once a term.
2. **Auto-extend.** For every occurrence lost to a closure, add one at the end
   of the series if that slot is free. Problems: the end of the season is
   often the summer break; the slot may not be free; invoices for the season
   may already be out.
3. **Offer a replacement.** Find the nearest free equivalent slot (same space,
   same week) and offer it to the org admin as a hold they can accept.
   Nicest, most work. Possibly reuses the waitlist offer machinery.
4. **Credit instead of refund.** Finance's preference: closures on series
   produce account credit rather than card refunds. That's billing's call
   (ADR 0012 territory) but affects what we tell the club.

Nobody has decided whether a closure on a *series* occurrence should be
treated any differently from one on a one-off booking. Finance (Mark Doyle)
says "probably not, but check with legal about the hire agreement wording".
Not checked, as far as we know.

## If you're asked by a club

Tell them the truth: closed sessions are refunded in full, the season isn't
extended automatically, and the bookings officer can add a make-up session
by hand if there's space.
