---
kind: decision
status: verified
---

# ADR 0006: Paybridge as card payment provider

- Date: 2023-06-29
- Deciders: Tom Ellery, Aisha Okafor; Janet Morley (Finance) consulted;
  council Information Security signed off the PCI scope.

## Context

Residents must pay by card when they book. The council already has a
merchant agreement with Paybridge for parking permits and the garden waste
service, so Finance get one settlement report and one set of fees. The
alternatives were the council's legacy payment portal (iframe-based, no
webhooks, no partial refunds) and signing up with another provider (new
procurement, months).

Information Security's requirement: card details must never touch our
servers. That rules out anything where we render the card form ourselves
(see `docs/constraints.md`).

## Decision

Use Paybridge **hosted checkout** plus **webhooks**:

- We create a checkout session server-side (`POST /checkout/sessions`) with
  the amount and our reference, and redirect the resident to Paybridge.
- We only treat a payment as real when we receive a signed
  `payment.succeeded` webhook. The browser redirect back to us is never
  trusted.
- Refunds go through the Paybridge refunds API, to the original card only.
- We store Paybridge's ids (`paybridge_payment_id`, `paybridge_refund_id`)
  and amounts, nothing else about the card.
- Every raw webhook is stored in `paybridge_events` before acting on it.
- Organisations that pay by invoice don't use Paybridge at all (bank
  transfer; see `docs/billing/invoicing.md`).

## Consequences

- PCI scope is SAQ A. Good.
- We depend on webhooks arriving promptly. When they're late, holds expire
  under paying customers. This has bitten us (March 2024) and is the reason
  for the hold-length change and the outage runbook.
- Webhooks are at-least-once, so everything that handles them must be
  idempotent. We knew that in theory. We learned it properly in 2024; see
  `docs/findings/billing-webhook-duplicates-2024-11.md`.
- Paybridge's settlement report is per UTC day and nets fees, which doesn't
  match how Finance want income reported. Reconciliation is its own job.
- API keys expire every two years and nobody gets told. (July 2025.)
