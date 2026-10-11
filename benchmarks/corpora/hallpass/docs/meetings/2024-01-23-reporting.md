# Reporting catch-up, 23 Jan 2024

Present: Priya (dev), Tom (dev), Janet Morley (Finance, income & debt), Sam
Reid (Leisure Services ops manager). Notes: Tom.

## 1. Income report doesn't match Paybridge

Janet: December income in Hallpass was £3.1k less than the Paybridge
settlement for December. Took her two days to work out why.

Reason: Hallpass report counts payments by `payments.created_at`, Paybridge
settles in batches (T+2) and counts refunds on the day they're issued.
Also the block bookings for the January netball league were all paid in
December.

Discussion: Janet doesn't actually want it to match Paybridge - she has the
Paybridge report for that. What finance need from us is income *by the month
the facility was used*, because that's how it goes to the cost centres.

**Agreed:**
- Income report recognises money on the local date of the booking start,
  not the payment date.
- Refunds net off against the month of the original booking, not the month
  the refund was issued. (Janet: "otherwise March looks terrible every year
  because of the Easter closures".)
- Invoice payments: count once the invoice is marked paid, attributed to
  booking months via invoice lines.
- Report gets a footnote saying it won't reconcile to Paybridge month to
  month.

Tom to change `reports/income.py`. No ADR - Priya: "it's a report definition,
not architecture". (Fair, but someone will ask in a year.)

## 2. Usage report: no-shows

Sam wants no-shows visible. Currently we have no way of recording them,
they're just confirmed bookings nobody turned up to.

- Add a `no_show` status. Staff mark it from the day sheet.
- In the usage report, no-shows count as *used* hours (space was blocked) but
  get their own column.
- Sam would like to "do something" about repeat no-shows. Parked for a later
  meeting, needs Leisure Services policy first.

## 3. VAT

Janet raised that the income report shows VAT on everything at 20%. Some
hires are exempt (sports lets to clubs for a series of sessions can be
exempt; one-off lets generally aren't). She'll come back with the rules.
Until then the VAT column is "indicative only".

(Update March 2024: she hasn't, we've chased once.)

## 4. Read replica for reports

Priya suggested running reports off hp-db-02 so finance's year-end runs don't
slow the booking site. Infra OK in principle. Not urgent at current volumes.
Nobody owns it.

## Actions

- Tom: income recognition change (done, v2.3.0)
- Priya: `no_show` status migration + day sheet button (done, v2.4.0, behind
  `no_show_tracking`)
- Janet: VAT exemption rules
- Sam: no-show policy proposal
