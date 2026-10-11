---
kind: constraint
status: verified
---

# Privacy constraints

Hallpass processes personal data for the council (the controller; Leisure
Services is the information asset owner). DPIA signed off May 2023, reviewed
November 2023 - the review produced ADR 0010 and the consents table. These
rules come out of it. If a change would break one, talk to Information
Governance (IG) first.

## What we may collect

- Residents: email (required), full name (required), UK mobile, postcode.
  **Nothing else.** No date of birth, gender or address lines.
  `is_in_borough` is derived from the postcode for pricing.
- Concessions are checked by Leisure Card number or a yes/no flag. No benefit
  details or evidence documents are stored.
- Organisations: name, type, charity number, billing email and address.
  Members are residents.
- Staff: council email, name, role.
- Booking notes must not hold anything about a hirer's health, disability or
  circumstances. Accessibility needs go in the dedicated yes/no fields.
  Facility staff have been reminded twice.

## Where it may go

- Email: the council's own SMTP relay only.
- SMS: TextHub (UK hosting, DPA on file). Only the number and message text.
- Card data never touches Hallpass; Paybridge hosted checkout collects it.
- Newsletter export: only residents whose latest `marketing` consent is true.
- No analytics or tracking scripts. The only cookie we set is the session
  cookie (strictly necessary).
- Staging holds an anonymised copy of production. The anonymiser is
  imperfect, so staging must never send real email or SMS.
- Logs: ids only, never emails, phone numbers, names or postcodes.

## Retention

ADR 0010: financial records 6 years from the end of the financial year,
everything else 2 years after last activity, then anonymise. Weekly job
`purge_personal_data`.

## Consent

- Marketing and photography: opt-in only, recorded in `consents` with
  source and time. Never pre-ticked.
- Service messages (confirmations, cancellations, login links, refunds): no
  consent needed. Email reminders count as service messages and are on unless
  the customer turns them off.
- **SMS reminders: believed to be opt-in by default** - no texts unless the
  customer opted in. This is the team's assumption and has not been verified
  (sign-up form default, the 2023 imported consents, and the legal basis are
  all unchecked). Details in `docs/notifications/reminders.md`.
- Waitlist offers and closure notices are also texted to anyone with a mobile,
  without a consent check. Not reviewed by IG.

## Individuals' rights

- Subject access: service desk forwards to IG; a superuser runs the SAR
  export (bookings, payments, consents, outbox rows) and sends it to IG, not
  to the requester. One calendar month.
- Erasure: superuser anonymises the account (`retention.anonymise_resident`,
  reason `erasure_request`). Financial records inside the 6-year window stay;
  IG explain why.
- Rectification: customers edit name, phone and postcode themselves; email
  changes go through the service desk.

## Who can see what

Contact details are visible to facility staff, finance and superusers. Org
admins see their members' names and emails, not phone numbers. Superuser
impersonation is audited.
