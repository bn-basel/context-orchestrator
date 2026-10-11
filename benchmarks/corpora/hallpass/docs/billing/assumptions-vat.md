---
kind: constraint
status: assumption
---

# VAT assumptions (not confirmed by Finance)

**Status: assumption.** Everything on this page is what the code does and
what we *believe* is right. None of it has been confirmed in writing by
Finance or the council's VAT adviser. Treat with care.

## A1. Registered charities are VAT-exempt for hires

**What the code does.** `billing/vat.py::treatment_for` returns `EXEMPT`
for any organisation with a `charity_number`. Their invoice lines show no
VAT. Card bookings aren't affected (residents pay the gross tariff price
either way; charities on card pay the same gross price — we just don't show
a VAT split to them).

**Where it came from.** The paper booking form used before Hallpass had
"Registered charities: no VAT" printed at the bottom. Tom copied the rule
across when he built invoicing in early 2024. No one checked whether the
form was right, or still right.

**Why we doubt it.** As far as any of us understand it, VAT relief for
charities is narrow and mostly about what the charity *buys* for specific
purposes; it isn't a general "charities don't pay VAT". Hiring a meeting
room is normally either exempt for *everyone* (a letting of land, if the
council hasn't opted to tax that building) or standard-rated for everyone.
Whether the hirer is a charity probably doesn't come into it. But we're
developers, not VAT advisers.

**What we've done about it.**
- Jan 2024 reporting meeting: Janet Morley (Finance) took an action to send
  us the VAT exemption rules. Chased March 2024. Chased again Oct 2024.
- Sept 2025: raised again during the finance guide review. "We'll look
  at it after year end."
- Nothing in writing yet.

**What changes if it's wrong.**
- Delete the charity branch in `treatment_for` (and its test,
  `test_charity_is_exempt`).
- Charity invoices since Feb 2024 under-show VAT. Because the VAT split is
  computed at render time (we only store gross), re-rendering will show the
  "right" VAT on the same gross total — i.e. the charity paid the right
  *amount*, we just reported the wrong *split*. Finance would need to decide
  whether that needs correcting with HMRC. Affected invoices:

  ```sql
  SELECT i.number, i.issued_at, o.name, i.total_pence
    FROM invoices i JOIN organisations o ON o.id = i.organisation_id
   WHERE o.charity_number IS NOT NULL AND i.status <> 'void'
   ORDER BY i.issued_at;
  ```

  (About 140 invoices across 9 charities as of Sept 2025.)
- If, on the other hand, the tariff for charities was *set* net of VAT on
  the assumption they'd pay none, then the gross price is wrong too. We
  don't know whether that's how the 2024 tariff was built. Ask Finance.

## A2. The "series of lets" exemption applies at 10+ sessions

We apply exemption to sports halls and pitches booked by an organisation
in a series of 10 or more. The real HMRC conditions (as we understand them)
also require the sessions to be at least a day apart, to be for the same
activity, and for the hirer to have exclusive use. We check none of those.
We also count the whole series even if sessions were later cancelled.
Probably fine for the clubs that actually do this. Not confirmed.

## A3. Meeting rooms and music rooms are standard-rated

We charge 20% on everything that isn't covered by A1 or A2. That assumes
the council has opted to tax all its community buildings. Northgate
Community Centre may be different (it was transferred from the parish
council in 2019). Unknown.

## A4. VAT on cancellation charges

Late-cancellation lines on invoices get the same VAT treatment as the
booking would have had. Some guidance treats cancellation charges as
compensation (outside the scope of VAT). We picked "same as the booking"
because it was simpler. Not confirmed.

---

If you're from Finance and reading this: a one-line email confirming or
correcting each of A1–A4 would let us take this page down.
