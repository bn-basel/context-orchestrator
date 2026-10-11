"""Accounts: residents, organisations, staff roles and passwordless login.

    residents.py      resident (customer) records, registration, profile edits
    organisations.py  clubs/groups/charities and their members
    roles.py          Principal, require_role, org admin checks
    auth.py           magic-link login (ADR 0004)
    sessions.py       signed session cookies
    consents.py       SMS / marketing consent records
    retention.py      anonymisation job (ADR 0010)

Nothing here sends mail directly; login links go through the notifications
outbox like everything else.
"""
