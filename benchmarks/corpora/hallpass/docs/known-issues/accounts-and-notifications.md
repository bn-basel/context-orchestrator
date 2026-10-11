---
kind: known_issue
status: verified
---

# Known issues: accounts and notifications

Keep this honest. When something's fixed, delete it here and say so in the
CHANGELOG.

## 1. SMS sent twice (sometimes three times) when the worker retries

**Severity:** medium - money, complaints ("why did you text me three
times?"), and people thinking they have two bookings.

The dispatcher marks a row `sending`, calls TextHub, then marks it `sent`. If
TextHub accepts the message but our read times out (5 s), we treat it as a
transient failure and retry 1, 2, 4... minutes later. TextHub v1 has no
idempotency, so every retry is another text. The same happens if the worker
dies between the call and the update, and when the stuck-row reaper resets
rows in a batch that is just slow.

Numbers: about 0.8% of SMS rows in February 2025; see
`docs/findings/notifications-sms-duplicate-sends.md`.

Workaround: none automatic. Don't reset `dead` SMS rows without checking the
TextHub portal.

Fix: TextHub v2 with `Idempotency-Key: outbox-<id>` (HP-619). A stopgap was
discussed - on a read timeout mark the row sent as "unconfirmed" instead of
retrying - but it swaps duplicates for occasional lost reminders and the
product owner preferred duplicates. The strict xfail
`test_read_timeout_then_retry_sends_once` will XPASS, which fails the run,
once this is fixed.

Email behaves the same, but the per-row Message-ID means most mail clients
hide the copy.

## 2. Are SMS reminders really opt-in?

We assume SMS reminders are opt-in by default and the code says so
(`consents.DEFAULTS`). Unverified: whether the sign-up form pre-ticks the
box, what the ~4,000 imported consent rows really mean, and what legal basis
IG think we rely on. See `docs/notifications/reminders.md`.

## 3. STOP doesn't stop everything

STOP records an `sms_reminders` opt-out. Waitlist offers and closure texts
don't look at consent, so they keep coming. Same with the `sms_reminders`
flag: it only covers reminders.

## 4. Mail scanners use up login links

Links are redeemed on GET, so Outlook Safe Links and similar products that
open links to scan them log the "scanner" in and the real click then says
"already used". Mostly schools and the hospital trust. Fix: a confirm page
with a button (POST). Workaround: personal email address.

## 5. Older link stops working once a newer one is used

By design (single use via `last_login_at`), but it's the number one login
complaint. The error now says "use the newest email we sent".

## 6. Staff links aren't single use

`staff_users` has no `last_login_at`, so a staff link works repeatedly for
its 20 minutes. Needs a migration. Low risk while staff accounts are few.

## 7. Can't log a resident out everywhere

Sessions are stateless signed cookies. Stolen phone = wait 30 days or change
the account email. Fix needs a session version column on `residents`.

## 8. Ex-club secretaries keep getting reminders

Removing someone from an organisation leaves future org bookings in their
name. Needs "transfer bookings". Staff can reassign single bookings meanwhile.

## 9. Nobody is told when they're added to an organisation

`add_member` is silent. The `org_member_added` template was designed and
never written.

## 10. Login emails wait behind bursts

Login links are claimed first, but a batch already claimed has to finish. If
TextHub is timing out, a batch of 200 can take minutes and the login email
sits behind it. One of the reasons the read timeout went from 10 s to 5 s,
which made issue 1 worse.

## 11. Delivery receipts are thrown away

No provider message id column, so TextHub receipts can't be matched to rows.
We can't tell "sent" from "delivered" for SMS.

## 12. Retention leftovers

- `audit_log` is append-only; entries written before mid-2024 sometimes have
  names in `details`. Can't scrub them. IG aware.
- No 6-year purge of financial records yet (first needed by 31 March 2029).
- Un-cancelled bookings never get a reminder (`reminder_queued_at` stays set).
