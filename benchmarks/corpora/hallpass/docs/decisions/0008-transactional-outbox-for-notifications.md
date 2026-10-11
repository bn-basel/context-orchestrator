---
kind: decision
status: verified
---

# ADR 0008: Transactional outbox for notifications

Status: accepted (2023-08)

## Context

Early Hallpass sent confirmation emails inline, right after the booking
INSERT and still inside the request. During user testing at Eastfield,
before the 1.0 release:

1. When the transaction rolled back after the email had gone (e.g. the
   exclusion constraint from ADR 0009 caught a double booking at commit),
   people got "Booking confirmed" for a booking that didn't exist.
2. When the SMTP relay was slow, booking requests took 20+ seconds and timed
   out at the load balancer, so people clicked again.

SMS (TextHub) was coming next and would be slower and flakier.

## Decision

Every outgoing message is written to `notifications_outbox` in the same
transaction as the change that causes it. A worker job (`dispatch_outbox`,
every minute) sends pending rows. Roll back the business change and the
message disappears with it.

- Domain code calls `notifications.outbox.enqueue(conn, template=..., <id>=...)`
  and never imports a sender.
- Rows carry `status` (pending, sending, sent, failed, dead), `attempts`,
  `not_before` and `last_error`.
- The dispatcher claims rows with `FOR UPDATE SKIP LOCKED` and commits
  `sending` before calling the provider; no transaction is held open across
  network I/O.
- Exponential backoff, `dead` after 6 attempts.

## Consequences

- Up to a minute's delay. Fine for confirmations and reminders; login links
  are claimed first.
- **Delivery is at-least-once.** A send that succeeds but isn't recorded is
  sent again. Accepted for email ("a duplicate email beats a lost one"). SMS
  came later and nobody revisited this; for SMS a duplicate costs money and
  annoys people. See the known issues page.
- The outbox doubles as the "did they get the email?" history for the
  service desk, so it is personal data and falls under ADR 0010.
