---
kind: doc
status: verified
---

# Holds and confirmation

When a resident picks a slot and presses "Book and pay" we:

1. validate the window (on the half hour, ≤ 4h, not closed),
2. ask billing for a price (`hallpass.billing.pricing.quote_price`),
3. insert a `bookings` row with `status = 'held'` and
   `hold_expires_at = now + 15 minutes`,
4. billing creates a Paybridge hosted checkout for `price_pence` and the
   resident is redirected to it.

The hold blocks the slot exactly like a confirmed booking (it's inside the
exclusion constraint's `WHERE`), so nobody else can take it while the resident
is typing their card details.

Note `place_hold` doesn't check opening hours. The public page only offers
open slots so it doesn't matter there, but the API will accept a 06:00 hold on
a hall that opens at 08:00 if you call it by hand. Staff do this on purpose
for early set-ups.

## Hold length

15 minutes, from `HALLPASS_HOLD_MINUTES` (`core.config`). It was 10 at
launch and went to 15 in 2.5.0 (June 2024) after the holds meeting in May
2024 — people on phones kept running out of time on the 3-D Secure step. It's
an env var, not a feature flag, so changing it needs a restart.

## Confirmation

Paybridge calls our webhook; billing records the payment and calls
`bookings.lifecycle.confirm(booking_id, paybridge_payment_id=...)`. Zero-price
bookings (100% concession, staff comps) are confirmed by billing without going
to Paybridge at all.

`confirm` is idempotent: Paybridge sometimes delivers the same event twice and
the second call just returns the already-confirmed booking (no second email).

## Expiry

The worker's release-holds job (`jobs.release_expired_holds`) runs every
minute and cancels holds past `hold_expires_at` with
`cancel_reason = 'hold_expired'`. No email — the resident abandoned checkout,
or is still on it.

### Paid after expiry

It happens. If the webhook arrives for a hold that's already been released:

- if the slot is still free, the booking is revived (status back to
  confirmed). Customer never knows.
- if someone else has taken it, `confirm` raises `HoldExpired`. What happens
  to the money is billing's business. The 2024 meeting notes say "automatic
  full refund"; the current billing code flags the payment
  (`needs_attention`, `paid_after_hold_expired`) and staff refund or rebook
  by hand. Check with billing before telling a customer either way.

## Organisations on account

`book_on_account` skips the hold and Paybridge entirely: it inserts the
booking as confirmed. The invoice line is created by billing's monthly invoice
run, not at booking time.

## Waitlist offers

A hold created by a waitlist offer gets a longer expiry (2 hours, see
`waitlist.OFFER_TTL`) because the person isn't sitting at checkout — they're
getting an email out of the blue.
