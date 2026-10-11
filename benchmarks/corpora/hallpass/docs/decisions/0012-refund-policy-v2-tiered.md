---
kind: decision
status: verified
---

# ADR 0012: Refund policy v2 — tiered by notice period

- Date: 2024-01-17
- Deciders: Tom Ellery, Priya; Sam Reid (Leisure ops) and Janet Morley
  (Finance) for the tiers
- Supersedes ADR 0007. Shipped in 2.1.0 (2024-02-06).

## Context

Under v1 (full refund up to 24h before) residents learned that holding a
popular slot "just in case" cost nothing as long as they cancelled the day
before. Leisure ops counted 212 cancellations of Friday/Saturday evening
hall bookings with 24-48h notice in Oct-Dec 2023; most of those slots went
unused because nobody re-books a hall for tomorrow night.

Options considered:

1. Keep v1, add a £5 admin fee. Finance disliked partial-pound refunds on
   cheap bookings (music rooms are £8/h) and the fee is a "charge", which
   brings VAT questions.
2. Move the cut-off to 7 days. Simple, but harsh for genuine illness.
3. Tiered refund by notice. Chosen.

## Decision

Refund for a resident cancelling a card-paid booking:

| Notice before start | Refund |
|---|---|
| 7 days or more | 100% |
| 48 hours to 7 days | 50% |
| under 48 hours | none |

- **Notice is measured from the moment of cancellation to the booking's
  start time**, in elapsed time.
- 50% is rounded half-up to the penny (ADR 0002).
- If the **council** cancels (closure, maintenance, blackout), 100%
  regardless of notice.
- Finance-role staff can refund any amount up to what's left on the payment,
  with a reason. That's the escape hatch for illness and complaints.
- Recurring/block bookings: each occurrence is treated on its own notice.
- Organisations on invoice: the same tiers, expressed as a *cancellation
  charge* on the next invoice instead of a refund (charge = price minus
  what a card customer would get back).
- No-shows get nothing (no cancellation, no refund).

## Consequences

- The cancel page has to show the refund before the resident confirms, so
  billing exposes a preview (`refunds.refund_preview`).
- "7 days" in elapsed time means 168 hours. Across a clock change the
  wall-clock "same time last week" is 167 or 169 hours away. We accepted
  that as an edge case at the time; it has produced a handful of complaints
  each spring since.
- v1 stays in the code behind `refund_policy_v2` so Finance can revert
  without a deploy. The flag was added (already on) in April 2024 when
  flags arrived (ADR 0014). It has never been turned off.
- The tier is stored on each refund (`refunds.policy_tier`) since 3.2. Older
  refunds have it NULL and you have to work it out from the dates.
