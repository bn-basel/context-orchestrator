---
kind: finding
status: verified
---

# Investigation: duplicate SMS reminders (March 2025)

Prompted by a councillor forwarding a complaint: a resident got three
identical reminder texts for a badminton booking on 4 March. The service desk
had logged 14 similar "texted twice" calls since January.

Investigated by mk, with TextHub support (their ticket TH-20931).

## Method

- All `channel = 'sms'` outbox rows created in February 2025: 6,412.
- TextHub's message log for the same month, exported as CSV from the portal,
  joined on `client_ref = 'outbox-' || id`.
- Counted rows with more than one TextHub message for the same client_ref.
- Worker logs for the same period (we don't store TextHub's message id
  anywhere else).

## Results

| TextHub messages per outbox row | Rows | Share |
|---|---|---|
| 1 (correct) | 6,358 | 99.16% |
| 2 | 47 | 0.73% |
| 3 | 6 | 0.09% |
| 0 (permanent failures, STOP) | 1 | 0.02% |

53 rows affected, 59 extra texts - under 1% extra spend. The complaints cost
more than the texts.

Causes:

1. **Read timeout after acceptance - 51 rows.** Typical pattern: TextHub log
   shows the message accepted at 08:00:03.8; our row has `last_error =
   'texthub read timeout'`; a second accepted message two minutes later.
   TextHub confirmed their p99 response time was over 5 s on 11 February
   mornings (a database migration on their side). The 08:00 release of
   quiet-hours reminders makes it worse because we send one at a time.
2. **Reaper - 2 rows.** On 18 February one dispatcher run took over 10
   minutes because of repeated timeouts; the next run's reaper put rows back
   to pending while the first run was still working through them.
3. **Worker killed between send and update - none found** this month,
   possible in principle.

The read timeout went from 10 s to 5 s in November 2024 (2.6.0) so slow
TextHub calls stopped delaying login emails. Comparing August-October 2024
with December 2024-February 2025, the duplicate rate went from about 0.2% to
0.8%. That change made it noticeably worse.

## Conclusions

- Root cause is ours: at-least-once delivery from the outbox (ADR 0008)
  plus a provider API with no idempotency. Retrying after a read timeout is
  unsafe with TextHub v1. Stop calling it "a TextHub glitch".
- Fix: TextHub v2 `Idempotency-Key`. TextHub confirmed a 24-hour dedupe
  window, far longer than our ~30-minute retry schedule.
- Cheap mitigations, not done:
  - dispatch SMS and email in separate runs so TextHub can't delay login
    links, then put the SMS read timeout back to 10 s;
  - make the reaper threshold longer than batch size x read timeout;
  - spread the 08:00 reminder release over half an hour.

## Follow-up

HP-619 moved to "next quarter" at the April 2025 planning meeting. Still
open.
