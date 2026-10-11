---
kind: doc
status: assumption
---

# Booking reminders

Every confirmed booking gets one reminder the day before. Introduced in
autumn 2023 (email first, SMS from 1.2.0) to cut no-shows at the sports halls (about 11% of evening
bookings then; roughly 6% by early 2024 according to the no-show report).

## How it works

Worker job `queue_reminders`, hourly. It takes confirmed bookings starting
*tomorrow* by the London calendar that have no `reminder_queued_at`, enqueues
a `booking_reminder` for each and stamps the booking. Running it twice queues
nothing new.

Channel (decided in `notifications/recipients.py`), one or the other, never
both:

- **SMS** if the `sms_reminders` flag is on, the customer has a mobile
  number, **and** they have opted in to SMS reminders;
- **email** otherwise (unless they've turned off email reminders too).

## SMS reminders are opt-in by default (assumption)

The team's understanding is that SMS reminders are **opt-in**: nobody gets a
reminder text unless they ticked "Text me reminders" at sign-up or switched
it on in their account. `consents.DEFAULTS["sms_reminders"]` is False, so a
customer with no consent row gets email.

This is an assumption, not a checked fact:

- The sign-up form is in the frontend repo. Nobody here has checked whether
  its "Text me reminders" box starts ticked. If it does, "opt-in" is opt-in in
  name only.
- About 4,000 consent rows with `source = 'import'` came from the old Access
  database in 2023, granted wherever the old "contact me by text" box was
  ticked. Whether that counts as consent to reminders was never asked.
- IG have never confirmed which basis we rely on. The DPIA wording
  ("consent for marketing and, arguably, reminders") predates reminders.

The question came up again at the February 2025 platform review because of
the TextHub bill; it was left as "check". Until someone does, don't build
anything else on the assumption.

## Edge cases

- **Quiet hours**: no texts 21:00-08:00 London time; those get
  `not_before = 08:00`. Most reminders are queued just after midnight and go
  at 08:00 the day before. A booking made late in the evening for the next
  day is reminded at 08:00 on the day itself.
- **Booked on the day** or after the last hourly run before it: no reminder.
- **Block bookings**: every occurrence is its own booking (ADR 0005), so a
  weekly club gets a reminder every week. No per-series opt-out.
- **Cancelled after queueing**: `cancel_pending` fails the queued row. Too late
  if it already went.
- **Un-cancelled bookings** keep `reminder_queued_at` and never get a new one.
- **Clock changes**: "tomorrow" is a London date and the day bounds come from
  `core.tz`, so the 23- and 25-hour days are handled. Checked October 2024.
