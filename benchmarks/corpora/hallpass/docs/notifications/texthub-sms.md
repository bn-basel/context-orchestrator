# TextHub (SMS) notes

TextHub is our SMS gateway, bought through the council's corporate comms
framework. Leisure Services has its own sub-account and is recharged per
segment (3.2p last time anyone checked - confirm before quoting it).

## Config

| Setting | Notes |
|---|---|
| `HALLPASS_TEXTHUB_API_BASE` | prod: TextHub's API. Staging: a mock. **Never** give staging the real key. |
| `HALLPASS_TEXTHUB_API_KEY` | Bearer token in the secrets store, rotated each April |
| `HALLPASS_TEXTHUB_SENDER_ID` | alphanumeric sender, so nobody can reply except STOP |
| feature flag `sms_reminders` | kill switch for reminder texts only (see below) |

## API version

We're on **v1**, which has no idempotency. The `client_ref` we send
(`outbox-<id>`) is only echoed back on delivery receipts; TextHub will accept
the same client_ref twice and send two texts.

v2 has an `Idempotency-Key` header with a 24h window, which would fix most of
our duplicate texts. Ticket HP-619. Known differences: OAuth client
credentials instead of a static token, new delivery receipt format, `to`
becomes a list. About a week including testing against their sandbox.

## Webhooks

- **Opt-out (STOP)**: records an `sms_reminders` opt-out for every resident
  with that number and cancels their pending texts. It does not stop
  waitlist offers or closure texts - those don't check consent.
- **Delivery receipts**: we receive them but have nowhere to put them (no
  provider id column on the outbox). They're logged and that's it.

Both are protected by a shared secret header; v1 doesn't sign payloads.

## The sms_reminders flag

Added (default off) in migration 0007 and switched on in production soon
after. Before that, stopping reminder texts during the January 2024
double-sending episode took an emergency deploy - one of the reasons for ADR
0014. The flag only controls whether `queue_reminders` may choose SMS.
Waitlist offers and closure texts ignore it. During the August 2024 billing
dispute we turned it off believing it stopped all SMS. It didn't.

## Segments and cost

Over 160 characters splits into 153-character segments. Any character
outside GSM-7 (pound sign, curly quotes, emoji, some accents) drops it to 67
per segment. A reminder for "Eastfield Leisure Centre - Sports Hall -
Badminton Court 3" is already 2 segments. Keep templates short; the template
test checks for this.

Volume: roughly 6-7k texts a month, mostly reminders.

## When TextHub is down

Retries run for about 30 minutes, then rows go `dead`. Reminders aren't
re-queued automatically (the booking already has `reminder_queued_at`). After
a long outage, a superuser can reset dead reminder rows for bookings that
haven't started - checking the portal first, see the duplicates issue.
