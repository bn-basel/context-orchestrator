from datetime import date, timedelta

import pytest

from hallpass.accounts import consents, retention
from tests.accounts.conftest import T0


@pytest.mark.parametrize(
    "today, expected",
    [
        (date(2026, 10, 11), date(2020, 3, 31)),
        (date(2026, 3, 31), date(2019, 3, 31)),
        (date(2026, 4, 1), date(2020, 3, 31)),
    ],
)
def test_financial_cutoff(today, expected):
    assert retention.financial_cutoff(today) == expected


def test_inactive_resident_anonymised(pg_conn, make_resident):
    rid = make_resident("old@example.org", "Old Timer", phone="+447700900123")
    n = retention.anonymise_expired(pg_conn, now=T0 + timedelta(days=740))
    assert n == 1
    row = pg_conn.execute(
        "SELECT email, full_name, phone, deleted_at FROM residents WHERE id = %s", (rid,)
    ).fetchone()
    assert row[:3] == (f"anon-{rid}@invalid", "Former customer", None)
    assert row[3] is not None


def test_dry_run_changes_nothing(pg_conn, make_resident):
    rid = make_resident("old@example.org")
    assert retention.anonymise_expired(pg_conn, now=T0 + timedelta(days=740), dry_run=True) == 1
    (deleted_at,) = pg_conn.execute("SELECT deleted_at FROM residents WHERE id = %s", (rid,)).fetchone()
    assert deleted_at is None


def test_recent_login_keeps_account(pg_conn, make_resident):
    make_resident(last_login_at=T0 + timedelta(days=400))
    assert retention.anonymise_expired(pg_conn, now=T0 + timedelta(days=740)) == 0


def test_newest_consent_row_survives(pg_conn, frozen, make_resident):
    rid = make_resident(last_login_at=T0 + timedelta(days=1100))
    consents.record(pg_conn, rid, "sms_reminders", True, source="signup_form")
    frozen(T0 + timedelta(days=10))
    consents.record(pg_conn, rid, "sms_reminders", False, source="account_page")
    retention.anonymise_expired(pg_conn, now=T0 + timedelta(days=1110))
    (n,) = pg_conn.execute("SELECT count(*) FROM consents WHERE resident_id = %s", (rid,)).fetchone()
    assert n == 1
    assert consents.current(pg_conn, rid, "sms_reminders") is False


# TODO: resident with a payment 3 years ago - should still be anonymised (the
# payment row stays). Needs billing fixtures; didn't want the dependency. -- mk
