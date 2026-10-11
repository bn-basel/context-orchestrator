---
kind: doc
---

# Organisations, clubs and groups

Design notes, mostly from when org booking was built (summer 2023), patched
since.

## What counts as an organisation

Anything that books as a group rather than a person: sports clubs, charities,
schools, faith groups, residents' associations, and a few commercial hirers
(fitness instructors renting the studio). `organisations.kind` is one of
club, charity, community_group, school, commercial. Billing uses it for the
community rate.

People belong to several organisations at once. The same handful of people
run half the clubs in Eastfield.

## Membership

`organisation_members(organisation_id, resident_id, role, added_at)`, role
'member' or 'org_admin'.

- The resident who registers the organisation becomes its first org_admin.
- Admins add members **by email**. The person must already have a Hallpass
  account; if not, the admin gets "ask them to register first". There's no
  invitation flow, and nobody is told they've been added.
- Removing a member deletes the row. An organisation must keep at least one
  org_admin; only a superuser can remove the last one (e.g. a club folding).

## Paying on account

New organisations pay by card like anyone else. Finance can set
`pays_by_invoice`, after which bookings are invoiced monthly to
`billing_email` and paid by bank transfer. The decision is made outside the
system (is the club real, has it paid before).

## Charities

`charity_number` is free text and isn't checked against the Charity
Commission register. Billing treats registered charities' hires as VAT
exempt - that's finance's area and I understand it isn't settled.

## On the list

- "Transfer bookings" when a secretary changes. Future bookings stay in the
  name of whoever made them, so the old secretary keeps getting reminders and
  the new one can't cancel without staff help.
- Tell people when they're added to an organisation.
- Members seeing invoices (admins only today).
