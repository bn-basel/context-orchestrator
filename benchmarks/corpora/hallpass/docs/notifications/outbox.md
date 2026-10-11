---
kind: doc
status: verified
---

# The notifications outbox in practice

The why is in ADR 0008. This is the how, for whoever is on support.

## Columns you'll look at

- `template` - `booking_confirmed`, `booking_cancelled`, `booking_reminder`,
  `series_confirmed`, `series_cancelled`, `series_sessions_closed`,
  `waitlist_offer`, `refund_issued`, `invoice_issued`, `magic_link`,
  `staff_magic_link`
- `channel` - email or sms; `recipient` - address or +44 number
- `context` - the values the template is filled with, captured at enqueue
  time (so a later change to the space name doesn't change the message)
- `status`, `attempts`, `last_error`, `sent_at`
- `not_before` - earliest send time. **While a row is `sending`, it holds the
  time it was claimed** (we had no column for that).

## Statuses

- **pending** - waiting, or waiting to retry (`not_before` in the future)
- **sending** - claimed by the worker; should last seconds. Over 10 minutes
  and the reaper puts it back to pending.
- **sent** - the relay or TextHub accepted it. Not the same as delivered.
- **failed** - permanent: invalid number, hard bounce, missing template,
  STOP received, booking cancelled before the reminder went. Never retried.
- **dead** - gave up after 6 attempts (about half an hour of backoff).

## Common jobs

Resend something that died:

```sql
UPDATE notifications_outbox
SET status = 'pending', attempts = 0, not_before = now()
WHERE id = 12345;
```

For SMS, check the TextHub portal first. "Dead after timeouts" sometimes
means TextHub sent it every time; resetting it adds another copy.

How backed up are we?

```sql
SELECT channel, status, count(*), min(not_before)
FROM notifications_outbox
WHERE status IN ('pending', 'sending')
GROUP BY 1, 2;
```

A few dozen pending just after midnight and at 08:00 is normal (reminders).
Thousands pending means the worker isn't running or a provider is down -
check cron on hp-app-01 first.

## Things that surprise people

- Who gets the message is decided in `notifications/recipients.py`, not by
  the caller. Org bookings with no resident go to the organisation's
  billing_email.
- Staff bookings made on someone's behalf still notify the resident. Intended.
- A big closure creates a burst (Eastfield sports hall, March 2025: ~600
  rows). The worker sends 200 a minute; login links are always claimed first.
- Rows older than 2 years are deleted (ADR 0010). Don't promise anyone a
  history further back.
