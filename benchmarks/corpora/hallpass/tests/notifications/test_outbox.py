from datetime import timedelta

import pytest

from hallpass.core import clock
from hallpass.notifications import outbox
from tests.notifications.conftest import T0


def _status(pg_conn, row_id):
    return pg_conn.execute(
        "SELECT status, attempts FROM notifications_outbox WHERE id = %s", (row_id,)
    ).fetchone()


class Failing:
    def __init__(self, exc):
        self.exc = exc

    def send(self, **kw):
        raise self.exc


def test_booking_confirmed_goes_to_resident_by_email(pg_conn, frozen, booking, senders):
    bid, _ = booking()
    [row_id] = outbox.enqueue(pg_conn, template="booking_confirmed", booking_id=bid)
    email, sms = senders
    assert outbox.dispatch_pending(pg_conn, email_sender=email, sms_sender=sms) == 1
    assert email.sent[0]["recipient"] == "priya@example.org"
    assert email.sent[0]["context"]["space_name"] == "Studio 2"
    assert sms.sent == []
    assert _status(pg_conn, row_id) == ("sent", 0)


def test_waitlist_offer_also_texts(pg_conn, frozen, booking):
    _, rid = booking()
    (wid,) = pg_conn.execute(
        "INSERT INTO waitlist_entries (resident_id, space_id, starts_at, ends_at) "
        "SELECT %s, space_id, starts_at, ends_at FROM bookings LIMIT 1 RETURNING id", (rid,)
    ).fetchone()
    ids = outbox.enqueue(pg_conn, template="waitlist_offer", waitlist_entry_id=wid)
    channels = pg_conn.execute(
        "SELECT channel FROM notifications_outbox WHERE id = ANY(%s) ORDER BY channel", (ids,)
    ).fetchall()
    assert channels == [("email",), ("sms",)]


def test_rolls_back_with_the_caller(pg_conn, frozen, booking):
    """The whole point of ADR 0008."""
    bid, _ = booking()
    with pytest.raises(RuntimeError):
        with pg_conn.transaction():
            outbox.enqueue(pg_conn, template="booking_cancelled", booking_id=bid)
            raise RuntimeError("cancel failed")
    (n,) = pg_conn.execute("SELECT count(*) FROM notifications_outbox").fetchone()
    assert n == 0


def test_login_links_jump_the_queue(pg_conn, frozen, booking, senders):
    bid, rid = booking()
    for _ in range(3):
        outbox.enqueue(pg_conn, template="booking_confirmed", booking_id=bid)
    outbox.enqueue(pg_conn, template="magic_link", resident_id=rid, context={"token": "r.1.2.3.x"})
    email, sms = senders
    outbox.dispatch_pending(pg_conn, batch_size=1, email_sender=email, sms_sender=sms)
    assert email.sent[0]["template"] == "magic_link"


def test_transient_failure_backs_off_then_dies(pg_conn, booking, senders):
    with clock.frozen(T0):
        bid, _ = booking()
        [row_id] = outbox.enqueue(pg_conn, template="booking_confirmed", booking_id=bid)
    flaky = Failing(outbox.TransientSendError("421 try later"))
    _, sms = senders
    for i in range(outbox.MAX_ATTEMPTS):
        with clock.frozen(T0 + timedelta(hours=i)):
            outbox.dispatch_pending(pg_conn, email_sender=flaky, sms_sender=sms)
        if i == 0:
            assert _status(pg_conn, row_id) == ("pending", 1)
    assert _status(pg_conn, row_id)[0] == "dead"


def test_permanent_failure_not_retried(pg_conn, frozen, booking, senders):
    bid, _ = booking()
    [row_id] = outbox.enqueue(pg_conn, template="booking_confirmed", booking_id=bid)
    outbox.dispatch_pending(pg_conn, email_sender=Failing(outbox.PermanentSendError("550")),
                            sms_sender=senders[1])
    assert _status(pg_conn, row_id) == ("failed", 0)


def test_stuck_sending_rows_are_reaped(pg_conn, booking, senders):
    with clock.frozen(T0):
        bid, _ = booking()
        [row_id] = outbox.enqueue(pg_conn, template="booking_confirmed", booking_id=bid)
        outbox._claim(pg_conn, 10)  # ...and the worker "dies"
    with clock.frozen(T0 + timedelta(minutes=11)):
        outbox.dispatch_pending(pg_conn, email_sender=senders[0], sms_sender=senders[1])
    # reaped back to pending (attempts 1) and then sent in the same run
    assert _status(pg_conn, row_id) == ("sent", 1)
