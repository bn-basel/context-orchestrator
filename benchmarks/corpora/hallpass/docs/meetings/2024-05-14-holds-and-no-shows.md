---
kind: doc
status: verified
---

# Holds and no-shows, 14 May 2024

Present: Priya, Tom, Gareth (infra, for item 3), Sam Reid (Leisure ops),
Laura Bennett (contact centre lead). Notes: Priya.

## 1. Hold length

Background: holds were 10 minutes at launch. The March Paybridge webhook delay
incident (see runbook) showed we auto-refund people when payment confirmation
arrives after the hold expires. Laura also says residents on phones with poor
signal regularly run out of time on the Paybridge page, especially when 3-D
Secure kicks them to their banking app.

Options discussed:
- 30 min: Sam against - popular slots (Friday 6pm hall) get "camped" by people
  who aren't serious.
- 15 min plus extend-on-return-from-Paybridge: complex.
- 15 min flat.

**Decision: 15 minutes, configurable via env var `HALLPASS_HOLD_MINUTES`.**
Tom asked whether it should be a feature flag (we'd just agreed flags in
ADR 0014) - Priya: flags are booleans, not numbers. Left as env var. Means
changing it needs a restart, which we'll live with.

No ADR written. If someone revisits: the 10→15 change shipped in v2.5.0.

## 2. Late payments

When a webhook confirms payment for a hold that has already expired:
- if the slot is still free → confirm the booking anyway (resident gets it)
- if someone else has it → automatic full refund, reason
  `hold_expired_before_payment`, email apologising

Tom pointed out the first branch means "expired" holds aren't really expired.
Agreed that's fine, it's what residents expect.

## 3. Worker on one box

Gareth asked why the worker only runs on hp-app-01. Answer: cron + advisory
locks; we could run it on both but it buys little. Agreed to leave it but
document the manual failover (now in the deploy runbook).

## 4. No-shows (follow-up from January)

Sam's proposal: three no-shows in 12 weeks → account suspended from online
booking for 4 weeks.

Laura: suspension will generate angry calls to her team, and a fair share of
"no-shows" are staff forgetting to mark people in. Also residents aren't told
anywhere that no-shows have consequences.

**Agreed (sort of):**
- No automatic suspension. Instead: after 3 no-shows in 12 weeks the
  resident gets flagged on the staff screen and the duty manager decides.
- No refund for a no-show (already true: no cancellation = no refund).
- Terms and conditions to be updated first (Sam to ask Legal).
- Revisit in 6 months with data.

Nobody wrote this down anywhere other than here. The "flag on staff screen"
bit has not been built as of this writing.

## Actions

- Tom: hold length 10 → 15 + env var
- Tom: late-payment confirm/refund logic in billing
- Sam: T&Cs wording on no-shows
- Priya: deploy runbook failover section
