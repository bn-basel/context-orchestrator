---
kind: decision
status: superseded
---

# ADR 0007: Refund policy v1 — full refund up to 24h before start

- Date: 2023-08-15
- Deciders: Tom Ellery; Sam Reid (Leisure ops) for the policy itself
- **Superseded by ADR 0012** (February 2024). Kept for history; the code path
  still exists behind the `refund_policy_v2` flag.

## Context

We need *some* refund rule for launch. The paper process was "ring the
centre and ask nicely", which in practice meant duty managers refunded
almost everything. Leisure ops wanted something simple enough to print on
the booking confirmation email.

## Decision

- A resident who cancels **24 hours or more** before the start gets a
  **full refund** to their card, automatically.
- Less than 24 hours: **no refund**. Staff can still refund manually if
  there's a good reason (illness, etc.).
- If the council cancels (closure, maintenance), full refund regardless.
- No admin fee.

## Consequences

- Easy to explain, easy to build: one comparison.
- Sam expected abuse ("people will block-book Friday evenings and cancel the
  day before") and that's what happened. By December 2023 popular evening
  slots were being cancelled at 25-30 hours' notice often enough that
  Leisure Services asked for a change. See ADR 0012.
