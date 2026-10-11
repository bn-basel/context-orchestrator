---
kind: doc
status: verified
---

# Organisation invoices

Some organisations pay monthly in arrears by bank transfer instead of by
card per booking: schools, the larger sports clubs, a few charities. Finance
decide who (credit check, usually a history of paying on time); a superuser
sets `organisations.pays_by_invoice = true`. There are about 60.

## Monthly run

Worker job `generate_invoices`, 1st of the month, 05:00, behind the
`org_invoicing` flag. It invoices **last calendar month in local time**.
Finance can also trigger a run from the back office (Invoices → Run), e.g.
after voiding an invoice. Re-running is safe: a booking already on a live
(non-void) invoice is skipped.

One invoice per organisation, one line per booking that *started* in the
month:

- confirmed → full price
- no-show → full price, description ends "(no-show)"
- cancelled with < 7 days' notice → "Late cancellation" line for
  price − (what a card customer would have got back). See ADR 0012.
- cancelled by us (`closure`) → nothing
- series with 10+ sessions in the month → 10% off each line

Invoice number: `HP-<FY>-<6 digits>`, e.g. `HP-2526-000417`. FY = April to
March. Numbers are MAX+1 under an advisory lock, so they're sequential
within a year but there can be gaps if a run is rolled back.

Due date: issue date + 30 days.

## VAT

`invoice_lines.amount_pence` is the **gross** (VAT-inclusive) amount.
Net and VAT are worked out when the PDF is rendered, per line, using
`billing/vat.py`:

- registered charity (has a charity number) → exempt *(assumption — see
  `assumptions-vat.md`)*
- sports hall / pitch, series of 10+ → exempt (HMRC "series of lets")
- everything else → standard 20%, VAT = gross × 1/6, rounded per line

Because it's computed at render time, changing the VAT rules changes what
an old invoice shows if it's re-downloaded. Finance keep the PDF as sent,
which is the legal document. Worth knowing before you "fix" vat.py.

## Getting paid

Bank transfers land in the council's main account. Finance match them by
the invoice number in the payment reference (when the payer bothered) and
record them in the back office (Invoices → Mark as paid). That creates a
`payments` row with `method = 'bank_transfer'`. Part-payments are fine.
When payments ≥ total, the invoice becomes `paid`.

We don't store the bank reference on the payment (no column); it's in the
audit log entry.

## Overdue

The `outstanding_invoices` report lists anything past due. Chasing is done
by Finance's debt team outside Hallpass. There was a plan to auto-suspend
online booking for organisations > 60 days overdue. Not built.

## Known oddities

- Block discount counts sessions per month, not per series (HP-377).
- VAT exemption for series uses the *whole* series size, the block discount
  uses the *monthly* count. They can disagree on the same line.
- Credit notes don't exist in Hallpass. Finance raise them in the finance
  system and void/adjust by hand.
- An organisation that switches from card to invoice mid-month: bookings
  already paid by card are skipped only because they're not `organisation_id`
  bookings... usually. Check the first invoice by eye.
