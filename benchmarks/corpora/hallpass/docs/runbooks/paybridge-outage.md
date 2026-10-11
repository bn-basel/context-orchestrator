---
kind: doc
status: verified
---

# Runbook: Paybridge is down (or slow, or weird)

Paybridge status page: status.paybridge.example. Support: the merchant support
line is on the shared ops password vault entry "Paybridge merchant" (our
merchant id is in there too). Priority support needs the account manager to
escalate; that's in the same entry.

## Symptoms and what they mean

| What you see | Likely cause |
|---|---|
| `UpstreamError provider=paybridge` on `/api/payments/checkout`, residents can't get to the payment page | Paybridge API down or our API key revoked/expired |
| Residents pay, land back on the return page, booking still "held" | Webhooks delayed or failing. Not an outage on its own; they retry. |
| Holds expiring with payments arriving after | Webhook delay > 15 min. Bad: people get refunded automatically and lose the slot. |
| `paybridge_events.signature_ok = false` rows appearing | Webhook secret rotated on their side, or someone's probing us |
| Lots of duplicate `event_id` conflicts in the log | Normal-ish; Paybridge redelivers. Only worry if confirmations are also missing. |

## Paybridge checkout down

1. Confirm on their status page / try the sandbox.
2. Turn on the banner: flip `payments_paused_banner`... we don't actually
   have that flag. For now ask the product owner to put a notice on the
   council website bookings page.
3. Holds will just expire; nothing is lost.
4. Organisations paying by invoice are unaffected.
5. Contact centre can still take bookings by phone using their terminal and
   the staff "record manual payment" screen.

## Webhooks delayed (the dangerous one)

The problem is the 15-minute hold. If Paybridge is taking card payments but
webhooks are late, holds expire, slots free up, someone else can take them,
and when the webhook arrives we auto-refund. Residents are (rightly) furious.

1. Extend holds: set `HALLPASS_HOLD_MINUTES=60` in
   `/etc/hallpass/hallpass.env` on both VMs and restart `hallpass-web`. (This
   is an env var, not a flag. Yes, it should be a flag. See the 2024 holds
   meeting notes.) Only affects new holds.
2. For holds already in flight, stop the expiry job temporarily: comment out
   the `release_holds` line in `/etc/cron.d/hallpass-worker` on hp-app-01.
   **Don't forget to put it back.** Set a reminder.
3. When webhooks resume, Paybridge redelivers everything it couldn't get
   through (a webhook we fail to process rolls back completely and gets a 5xx,
   so there is no half-processed backlog on our side). Events Paybridge never
   delivered at all:
   - pull "payments in the last N hours" from the Paybridge dashboard
   - compare against `SELECT paybridge_payment_id FROM payments WHERE
     created_at > now() - interval 'N hours'`
   - ask Paybridge support to redeliver the missing ones (they can, by event
     id or by time range). Don't hand-insert payments if you can avoid it.
4. Revert the hold length and re-enable expiry.

## Signature failures

If every webhook is failing the signature check:

1. Check whether someone rotated the webhook secret in the Paybridge
   dashboard (it emails the finance systems mailbox when that happens).
2. Update `HALLPASS_PAYBRIDGE_WEBHOOK_SECRET` on both VMs, restart web.
3. Failed deliveries get retried by Paybridge for 72h, so as long as you fix
   it within that window nothing is lost. We return 400 for bad signatures,
   which they treat as retryable. (It used to be 403. Either works.)

If it's a handful of failures from unfamiliar IPs, it's probably scanning.
Leave it, note it in the security log.

## After an incident

- Run the reconciliation for each affected day by hand:
  `hallpass-worker reconcile_paybridge` only does yesterday; for other days use
  `python -m hallpass.billing.reconciliation --day YYYY-MM-DD`.
- List auto-refunds caused by late webhooks (refunds with reason
  `hold_expired_before_payment`) and send them to Leisure Services so they
  can contact the residents.
- Short write-up in `docs/findings/` if it was more than an hour.

## History

- 2024-03-09 (Sat): Paybridge webhook delays of ~40 min during their
  platform migration. 23 auto-refunds. This runbook was written after.
- 2025-07-21: API key expired (they're valid 2 years, nobody had a reminder).
  45 minutes of no checkout. Calendar reminder now set for July 2027.
