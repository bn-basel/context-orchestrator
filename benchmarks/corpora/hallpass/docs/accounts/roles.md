---
kind: convention
status: verified
---

# Roles and who can do what

Last reviewed Jan 2025 (mk). Code: `hallpass/accounts/roles.py`. If you add
or change a `require_role(...)` call, update the matrix below in the same PR.

## The five roles

| Role | Who | Stored as |
|---|---|---|
| **resident** | Any member of the public with an account. The UI says "customer", older docs say "hirer" or "account holder". | a row in `residents` |
| **org_admin** | A resident who runs a club, charity or group | `organisation_members.role = 'org_admin'` for *that* organisation |
| **facility_staff** | Duty managers and reception at the centres and halls | `staff_users.role` |
| **finance** | Leisure Services finance officers (three people) | `staff_users.role` |
| **superuser** | The dev team plus two service desk leads | `staff_users.role` |

- org_admin is the only scoped role. Admin of the Rovers gives you nothing
  at the Allotment Society. Plain members (`role = 'member'`) can see the
  club's bookings and get closure notices; it's not really a role.
- A staff member has exactly one role. When an acting manager needed both
  facility and finance access (summer 2024) we made her superuser for six
  weeks. Not great.
- Staff can also have a resident account with the same email. Separate
  identities; which one you are depends on which login you used.
- Superuser is not implied by anything. Each endpoint lists `"superuser"`
  explicitly.

## Matrix (what the endpoints check today)

| Action | resident | org_admin | facility_staff | finance | superuser |
|---|:-:|:-:|:-:|:-:|:-:|
| Book / cancel own bookings | Y | Y | | | |
| Book and cancel for the organisation | | Y | | | Y |
| Add / remove organisation members | | Y | | | Y |
| See the organisation's invoices | | Y | | | Y |
| Day sheet, mark no-shows | | | Y | | Y |
| Book on someone's behalf (phone bookings) | | | Y | | Y |
| Closures / blackouts | | | Y | | Y |
| Discretionary refunds, invoices | | | | Y | Y |
| Price rules and concessions | | | | Y | Y |
| Usage report | | | Y | Y | Y |
| Income report | | | | Y | Y |
| Spaces and opening hours | | | | | Y |
| Staff accounts, feature flags | | | | | Y |
| Impersonate a resident, erasure | | | | | Y |

Facility staff can't edit opening hours themselves; they raise a service
desk ticket (about 5 a month). They keep asking.

## Refunds - the grey area

Facility staff can't issue refunds, but when a duty manager cancels a booking
(hall flooded) the cancellation code refunds according to policy (ADR 0012)
without anyone needing finance rights. The finance-only refund endpoint is
for discretionary refunds outside the policy.

## Impersonation

Superusers can "view as" a resident. Every request made that way is written
to `audit_log`. Don't make bookings while impersonating unless the resident
is on the phone and asked; use a facility staff phone booking instead so it
is attributed properly.
