---
kind: doc
status: verified
---

# Hallpass for Finance: how the money works

*For the Income & Debt team and anyone in Finance who needs to understand
Hallpass figures. No technical knowledge needed. Last reviewed with Janet
Morley, September 2025.*

## Where money comes from

There are two ways a hirer pays.

**By card, up front.** Almost all residents and most small groups. The
customer pays on Paybridge's payment page (the same provider the council
uses for parking and garden waste). Their booking is only confirmed once
Paybridge tells us the payment went through. Money settles to the council
account through Paybridge's normal daily settlement, minus Paybridge's fees.

**By invoice, monthly.** About 60 approved organisations (schools, larger
clubs, some charities). They book without paying. On the 1st of each month
Hallpass produces one invoice per organisation covering the bookings that
took place last month. Payment terms are 30 days, by bank transfer. When a
transfer arrives you record it against the invoice in the back office.

## What a booking costs

Prices come from the tariff you send us each year. They are stored
*including VAT where VAT applies*. A booking's price is calculated when it
is made and then fixed — if the tariff changes later, existing bookings
keep their original price.

Adjustments, in this order:

1. Residents living outside the borough pay 25% more.
2. One concession, if the resident holds one (Leisure Card 50%, under-18
   30%, over-65 25%, etc.). Only the best one counts; they don't add up.
3. 10% off for block bookings of 10 or more sessions — on organisation
   invoices only, in practice.

You may notice concession bookings sometimes cost **1 or 2 pence less**
than you'd calculate from the tariff. That's a known rounding quirk in how
Hallpass applies the discount to each half hour separately. It always
favours the customer and is a few pounds a month in total. It's on our list.

## Cancellations and refunds

Since February 2024 (before that it was "full refund up to 24 hours before"):

| Customer cancels... | They get back |
|---|---|
| 7 days or more before | everything |
| between 2 and 7 days before | half |
| less than 2 days before | nothing |
| we cancel (closure, maintenance) | everything |
| they don't turn up | nothing |

Refunds go back to the original card automatically, usually within a few
minutes of the cancellation; the bank then takes 3-5 working days.
Organisations on invoice don't get refunds — instead the late-cancellation
amount appears as a line on their invoice.

Your team can also make **discretionary refunds** (illness, complaints) in
the back office. Please always do this in Hallpass, not in the Paybridge
dashboard — refunds made directly in Paybridge are invisible to Hallpass
and make the reports wrong.

## Reports and why they don't match Paybridge

The Hallpass income report counts income **in the month the booking takes
place**, and nets refunds back against that month (agreed January 2024).
Paybridge's report counts money on the day it **settles**, net of fees.
These will never match month to month and aren't meant to.

What *should* match is individual payments. Every night Hallpass compares
the previous day's Paybridge settlement with its own records and emails the
finance systems mailbox with anything that doesn't line up. Types you'll see:

- **missing locally** — Paybridge took money we have no record of. Rare;
  always investigate.
- **missing remotely** — we think someone paid, Paybridge's file doesn't
  have it. Usually it's in the next day's file (timing), so check the next
  email before chasing.
- **amount mismatch** — different amounts. Investigate.
- **refund stuck** — Paybridge refunded, we still show it as in progress.
  Tell the developers.
- **refund unknown** — a refund made in the Paybridge dashboard.
- Penny differences (1-2p) are counted but not listed.

## VAT

Card prices are VAT-inclusive. On invoices, each line shows net and VAT.
Hallpass currently treats these as exempt from VAT:

- block bookings of 10+ sessions of sports halls or pitches by the same
  organisation;
- **all hires by registered charities.**

The second rule was carried over from the old paper forms and **has never
been confirmed by Finance.** We asked in January 2024. If it is wrong,
invoices to charities since 2024 have under-charged VAT. Please see
*VAT assumptions* (`assumptions-vat.md`) and tell us either way.

## Who to ask

Hallpass developers: the Digital team's service desk queue "Hallpass".
For anything urgent on a payment day (card payments failing), phone the
Digital duty number.
