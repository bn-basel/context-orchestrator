---
kind: decision
status: verified
---

# ADR 0004: Passwordless login with emailed magic links

Date: 2023-02-08
Deciders: Joanna T., Mehmet K. (Lewis from IT security consulted)

## Context

The old system (an Access database plus a contractor's web form) had
username/password accounts. In its last year about 40% of service desk calls
about bookings were password resets, and the 2022 audit found the password
table was unsalted SHA-1. Most residents book once or twice a year and never
remember a password anyway.

Options considered:

1. Passwords done properly (argon2, reset flow, lockout). Still a reset flow,
   still the calls.
2. GOV.UK One Login - not open to councils for this kind of service then.
3. "Sign in with Google/Microsoft" - excludes people; councillors uneasy.
4. Emailed one-time links.

## Decision

Residents log in by entering their email and clicking a link we email them.
We store no passwords.

- Links are signed tokens (HMAC with the app secret), not database rows.
- A link expires after 60 minutes and can be used once.
- Sessions last 30 days for residents.
- Registration asks for email and full name, then sends the first link.
- Staff use the same mechanism for now and move to council SSO (Azure AD)
  "later".

## Consequences

- Login depends on email deliverability. Login emails are sent ahead of
  everything else in the outbox (ADR 0008).
- Anyone with access to the inbox can log in. Same as any reset flow.
- Shared family email addresses mean shared accounts. Accepted.
- We need throttling on link requests or it's a free spam cannon.

## Later notes

- 2024: pen test recommended a shorter window; expiry cut from 60 to 20
  minutes (`HALLPASS_MAGIC_LINK_TTL_MINUTES`). Complaints from school and NHS
  addresses where mail is held for 10+ minutes followed.
- "Used once" is implemented by comparing the link's issue time with
  `residents.last_login_at`. `staff_users` has no such column, so staff links
  can be reused until they expire. Not what this ADR intended.
- The link is redeemed on GET. Mail scanners that open links consume them.
  A confirm-button page was suggested and never built.
- 2025: staff still on magic links, SSO never prioritised. Staff sessions are
  12h per IT policy ISP-07.
