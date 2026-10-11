from datetime import UTC, datetime, timedelta

import pytest

from hallpass.accounts import consents
from hallpass.core import tz
from hallpass.notifications import reminders
from tests.notifications.conftest import T0


def _queued(pg_conn):
    return pg_conn.execute(
        "SELECT channel, recipient FROM notifications_outbox WHERE template = 'booking_reminder'"
    ).fetchall()


def test_email_by_default_even_with_a_phone(pg_conn, frozen, booking):
    # No consent row => not opted in to SMS (consents.DEFAULTS).
    booking()
    assert reminders.queue_reminders(pg_conn, now=T0, include_sms=True) == 1
    assert _queued(pg_conn) == [("email", "priya@example.org")]


def test_sms_when_opted_in(pg_conn, frozen, booking):
    _, rid = booking()
    consents.record(pg_conn, rid, "sms_reminders", True, source="account_page")
    reminders.queue_reminders(pg_conn, now=T0, include_sms=True)
    assert _queued(pg_conn) == [("sms", "+447700900333")]


def test_flag_off_means_email_even_if_opted_in(pg_conn, frozen, booking):
    _, rid = booking()
    consents.record(pg_conn, rid, "sms_reminders", True, source="account_page")
    reminders.queue_reminders(pg_conn, now=T0, include_sms=False)
    assert _queued(pg_conn)[0][0] == "email"


def test_second_run_queues_nothing(pg_conn, frozen, booking):
    booking()
    reminders.queue_reminders(pg_conn, now=T0, include_sms=True)
    assert reminders.queue_reminders(pg_conn, now=T0 + timedelta(hours=1), include_sms=True) == 0
    assert len(_queued(pg_conn)) == 1


def test_only_tomorrow_local(pg_conn, frozen, booking):
    booking(starts_in=timedelta(days=3))
    booking(status="cancelled")
    assert reminders.queue_reminders(pg_conn, now=T0, include_sms=True) == 0


@pytest.mark.parametrize(
    "utc_now, local_hour",
    [
        (datetime(2025, 6, 10, 21, 30, tzinfo=UTC), 8),  # 22:30 BST -> 08:00 next day
        (datetime(2025, 6, 10, 5, 0, tzinfo=UTC), 8),  # 06:00 BST -> 08:00 same day
        (datetime(2025, 6, 10, 12, 0, tzinfo=UTC), 13),  # daytime: unchanged
        (datetime(2025, 10, 25, 22, 0, tzinfo=UTC), 8),  # 23:00 BST, clocks go back overnight
    ],
)
def test_quiet_hours(utc_now, local_hour):
    assert tz.to_local(reminders.next_allowed_sms_time(utc_now)).hour == local_hour
