from datetime import timedelta

import pytest

from hallpass.accounts import consents
from hallpass.core import clock
from hallpass.notifications import outbox
from hallpass.notifications.outbox import PermanentSendError, TransientSendError
from hallpass.notifications.sms_sender import TextHubSender, handle_stop
from tests.notifications.conftest import T0, FakeTextHub

CTX = {
    "first_name": "Priya",
    "space_name": "Studio 2",
    "facility_name": "Eastfield Leisure Centre",
    "time_text": "18:00-19:00",
    "booking_ref": "HP-B1001",
}


def send(hub, row_id=42):
    return TextHubSender(client=hub.client()).send(
        row_id=row_id, recipient="+447700900111", template="booking_reminder", context=CTX
    )


def test_ok_and_client_ref():
    hub = FakeTextHub(["ok"])
    assert send(hub) == "msg_1"
    assert hub.accepted[0]["client_ref"] == "outbox-42"
    assert "Studio 2" in hub.accepted[0]["body"]


def test_invalid_number_is_permanent():
    with pytest.raises(PermanentSendError):
        send(FakeTextHub(["invalid_number"]))


@pytest.mark.parametrize("step", ["500", "connect_timeout", "read_timeout"])
def test_transient(step):
    with pytest.raises(TransientSendError):
        send(FakeTextHub([step]))


@pytest.mark.xfail(
    strict=True,
    reason="KNOWN BUG: TextHub accepted the first attempt but we timed out reading "
    "the reply; the retry sends the text again. Needs TextHub v2 Idempotency-Key "
    "(HP-619). Remove the xfail when fixed.",
)
def test_read_timeout_then_retry_sends_once(pg_conn, booking):
    hub = FakeTextHub(["read_timeout", "ok"])
    sms = TextHubSender(client=hub.client())
    with clock.frozen(T0):
        bid, rid = booking()
        consents.record(pg_conn, rid, "sms_reminders", True, source="account_page")
        outbox.enqueue(pg_conn, template="booking_reminder", booking_id=bid)
        outbox.dispatch_pending(pg_conn, email_sender=None, sms_sender=sms)
    with clock.frozen(T0 + timedelta(minutes=2)):
        outbox.dispatch_pending(pg_conn, email_sender=None, sms_sender=sms)
    assert len(hub.accepted) == 1  # today: 2


def test_stop_opts_out_everyone_on_the_number(pg_conn, frozen):
    for email in ("mum@example.org", "teen@example.org"):
        pg_conn.execute(
            "INSERT INTO residents (email, full_name, phone) VALUES (%s, 'X Y', '+447700900222')", (email,)
        )
    assert handle_stop(pg_conn, phone="+447700900222") == 2
