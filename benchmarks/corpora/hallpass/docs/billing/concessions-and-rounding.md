---
kind: doc
status: verified
---

# Concessions, discounts and why the pennies don't add up

Written by Priya, April 2025, after Finance asked (politely, the third time)
why the "You saved" figure and the amount charged don't sum to the full
price on some bookings.

## What discounts exist

**Concessions** belong to a resident. Catalogue in `concessions` (code,
description, either `percent_off` or `pence_off`). Who holds which is in
`resident_concessions`, with a `valid_until` that front-desk staff set when
they check the card or proof.

| Code | Usual value | Proof |
|---|---|---|
| LEISURE_CARD | 50% | council Leisure Card (means-tested) |
| U18 | 30% | date of birth |
| OVER_65 | 25% | date of birth |
| DISABILITY | 50% | blue badge / PIP letter, etc. |
| CARER | 100% | carer accompanying a disabled hirer |
| STAFF_VOUCHER | £10 off | one-off vouchers handed out after complaints |

The table is the truth; that list is what was there when I wrote this.

- Only **one** concession applies — the one that saves the most on this
  booking. Over-65 *and* Leisure Card = 50%, not 75%.
- Concessions only apply to residents booking **for themselves**. Booking on
  behalf of an organisation = organisation's tariff, no concession.
- Out-of-borough residents pay +25% first, then the concession comes off.

**Block-booking discount**: 10% off when a series has 10+ sessions.
Stacks with a concession (applied after it). In practice:
- residents: bookings doesn't tell pricing how long the series is, so
  residents never actually get it. Known, nobody has complained;
- organisations: applied on the monthly invoice, counting only the
  sessions that fall in that month (HP-377).

## The rounding problem (HP-412)

ADR 0002 says: apply a percentage once, to the total, round half-up. The
concession code doesn't. It discounts every 30-minute slot separately and
**rounds each one down** (integer division).

Worked example — 2 hours in a meeting room at £27.50/h, Leisure Card 50%:

| | per half hour | 4 half hours |
|---|---|---|
| tariff | 1375p | 5500p |
| 50% per slot, floored | 687p (687.5) | **2748p** charged |
| 50% of total, half-up | | 2750p "should be" |

So the resident pays £27.48 instead of £27.50. Two pence in their favour.
Elsewhere:

- The checkout's "You saved £x" uses `discount_pence(total)`, half-up on
  the total: £27.50. Saved + paid = £54.98, not £55.00.
- A 50% partial refund (ADR 0012) is half-up on `price_pence`: 2748 → 1374.
  Fine. But on an odd price like 2749 it's 1374.5 → 1375.
- The income report computes "concession value" as gross × percent on
  totals, so it overstates concessions by the same pennies.
- Finance's own spreadsheet recomputes from the tariff and gets 2750.

The difference per booking is at most (number of slots − 1) pence for a
50% concession; for 30% it can be one penny either way after the
display figure is involved. Across ~1,900 concession bookings a month it's
a few pounds. Finance's view: "not material, but please fix eventually".

### Why not just fix it?

Two reasons, neither great:

1. Fixing it changes `price_pence` for *new* bookings only. Held/confirmed
   future bookings keep the old figure, so for a few months there'd be two
   behaviours in the data. Finance would rather have one consistent wrong
   than a mix. (Their words, roughly.)
2. The odd hourly rates that cause it (£27.50, £13.50...) are the ones
   Finance plan to round to whole pounds at the next tariff review anyway,
   which would make the problem mostly disappear.

The intended fix: discount the total with `core.money.percent_of`, then
spread it across slots with `split_evenly` so the lines still sum. There's
a strict xfail test (`test_concession_total_matches_percent_of_gross`)
that will start "failing" (XPASS) when someone does it — delete the xfail
marker then.

## Pence-off concessions

`STAFF_VOUCHER` is £10 off the booking. It's taken from the earliest slots
first and can't make a booking negative. If the booking is cheaper than the
voucher the remainder is lost — vouchers are single-use. Front desk know.
