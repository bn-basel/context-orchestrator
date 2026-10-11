---
kind: constraint
status: verified
---

# Constraints

Things that are fixed for us by law, council policy, contracts or the people
who run our infrastructure. These are not design preferences; changing any of
them needs someone outside the dev team to sign it off.

## Payments (PCI DSS)

- Card details must never touch Hallpass servers. We use Paybridge's hosted
  checkout page so we stay in the SAQ A scope. No embedded card fields, no
  "just collect the card number over the phone and type it in". Phone
  payments go through the contact centre's own terminal.
- We store only Paybridge's payment/refund ids and amounts.
- Refunds must go back to the original card. No refunds to a different card or
  as cash for card payments (council finance rule).

## Data protection (UK GDPR / DPA 2018)

- Hallpass processes residents' personal data under the council's public task
  basis for bookings, and consent for marketing and (arguably) reminders. The
  Data Protection Officer signed off the DPIA in Nov 2023; changes to what we
  collect need a DPIA update.
- Retention: 6 years for financial records, 2 years for everything else after
  last activity (ADR 0010). The retention job anonymises; it must not delete
  rows that finance or audit depend on.
- Data stays in the UK. Hosting is the council's own data centre. Any new
  third-party processor needs a data processing agreement and UK/adequacy
  hosting. (TextHub and Paybridge both have DPAs on file.)
- Subject access requests are answered by the Information Governance team
  using the staff export; we have 1 calendar month.

## Accessibility

- Public sector website: must meet WCAG 2.2 AA (Public Sector Bodies
  Accessibility Regulations 2018) and keep the accessibility statement current.
  The booking flow was last audited externally in Sept 2025.

## Platform

- PostgreSQL 16 on council-managed VMs. The DBA team supports PG only; no
  other datastores without a business case.
- Python 3.12 (the RHEL 9 VMs get it from AppStream). Upgrading Python means
  waiting for infra to package it.
- Outbound email only through the council SMTP relay. No SendGrid etc.
- No new paid SaaS without procurement (anything over £5k a year needs
  quotes; under that still needs a contract).
- Deploys only in the agreed change window (see `docs/runbooks/deploy.md`).
  Emergency changes need the duty manager's OK.

## Audit

- `audit_log` is append-only. The app DB role has no UPDATE/DELETE on it.
  Internal Audit read it directly for their annual review.
- Every refund, manual payment, price rule change, flag change and staff
  cancellation must write an audit_log row in the same transaction.

## Booking rules set by the service (not by us)

- Bookable on a 30-minute grid (ADR 0011).
- Residents can book up to 90 days ahead; organisations up to 12 months.
- Maximum single booking length is 4 hours for residents. Orgs have no limit
  but staff review anything over 8 hours.
- Facilities are shut overnight. Nothing is bookable between 23:00 and 06:00
  local.
