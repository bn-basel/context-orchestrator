---
kind: decision
status: verified
---

# ADR 0010: Personal data retention - 6 years for financial, 2 years otherwise

- Date: 2023-11-20
- Agreed with: Information Governance (Sarah P.) and the Leisure finance lead
- Before this: we kept everything forever, which the DPIA review flagged

## Context

The council's retention schedule says financial transaction records are
kept for "current financial year + 6 years". It has no entry for online
booking accounts, so IG asked us to propose one.

What we hold about a hirer: email, name, phone, postcode, bookings, payments
and refunds, invoices (organisations), consent decisions, notification
history (outbox), audit log entries.

## Decision

| Data | Kept for | Counted from |
|---|---|---|
| Payments, refunds, invoices, invoice lines, and their bookings | 6 years | end of the financial year (31 March) the record falls in |
| Everything else personal: profile, consents, outbox, memberships | 2 years | the account's last activity (login, booking or payment) |

- A scheduled job anonymises residents inactive for 2 years: email, name,
  phone and postcode are overwritten and `deleted_at` is set. The row stays
  because bookings and payments reference it. Financial rows are not
  touched; finance confirmed they need amounts and dates for audit, not the
  person's name.
- Outbox rows older than 2 years are deleted. Superseded consent rows older
  than 2 years are deleted; the latest decision per purpose is kept.
- Organisation memberships of anonymised residents are deleted.
- A 6-year purge of financial rows is still to be built. Nothing is old
  enough before 31 March 2029.
- Erasure requests: a superuser runs the same anonymisation on demand. Where
  financial records must be kept, IG explain that to the requester.

## Consequences

- No "did they get the email?" answers beyond 2 years. Accepted.
- The audit log is append-only, so audit entries that name a person can't
  be scrubbed. IG accepted this as an audit requirement.
- Reports counting unique customers see anonymised residents as distinct but
  nameless.
