import pytest

from hallpass.notifications import templates
from hallpass.notifications.outbox import PermanentSendError

SAMPLE = {
    "first_name": "Priya",
    "space_name": "Main Hall (badminton court 2)",
    "facility_name": "Northgate Community Centre",
    "date_text": "Sat 14 Mar",
    "time_text": "18:30-19:30",
    "booking_ref": "HP-B48213",
    "token": "r.1.1700000000.abcd.SIG",
}

SMS_TEMPLATES = ["booking_reminder", "waitlist_offer", "series_sessions_closed"]


@pytest.mark.parametrize("name", SMS_TEMPLATES)
def test_sms_fits_two_gsm7_segments(name):
    body = templates.render_sms(name, SAMPLE)
    assert not set(body) - templates.GSM7, "non GSM-7 character - costs double"
    assert templates.sms_segments(body) <= 2


def test_magic_link_email_contains_link():
    subject, body = templates.render_email("magic_link", SAMPLE)
    assert subject == "Your login link"
    assert "/api/account/magic-link/r.1.1700000000.abcd.SIG" in body


def test_missing_placeholder_is_permanent():
    with pytest.raises(PermanentSendError):
        templates.render_sms("booking_reminder", {"first_name": "x"})


def test_segments():
    assert templates.sms_segments("a" * 160) == 1
    assert templates.sms_segments("a" * 161) == 2
    assert templates.sms_segments("£" * 70) == 1
    assert templates.sms_segments("£" * 71) == 2
