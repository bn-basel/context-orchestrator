from __future__ import annotations

import hashlib
import hmac
import json
from unittest import mock

from hallpass.billing import webhooks
from hallpass.billing.payments import UnknownPayment
from tests.billing.conftest import FakeConn

SECRET = "whsec_test_abc123"
NOW = 1_740_000_000


def sign(body: bytes, secret: str = SECRET, ts: int = NOW) -> str:
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def event(event_id: str = "evt_1", type_: str = "payment.succeeded", **obj) -> bytes:
    data = {"object": {"id": "pay_123", "amount": 3600, **obj}}
    return json.dumps({"id": event_id, "type": type_, "data": data}).encode()


class TestSignature:
    def test_valid(self):
        body = event()
        assert webhooks.verify_signature(body, sign(body), secrets=[SECRET], now=NOW)

    def test_tampered_body(self):
        body = event()
        assert not webhooks.verify_signature(body.replace(b"3600", b"1"), sign(body), secrets=[SECRET], now=NOW)

    def test_old_timestamp(self):
        body = event()
        assert not webhooks.verify_signature(body, sign(body), secrets=[SECRET], now=NOW + 301)

    def test_missing_or_garbage_header(self):
        assert not webhooks.verify_signature(b"{}", None, secrets=[SECRET], now=NOW)
        assert not webhooks.verify_signature(b"{}", "nonsense", secrets=[SECRET], now=NOW)
        assert not webhooks.verify_signature(b"{}", "t=abc,v1=00", secrets=[SECRET], now=NOW)

    def test_our_rotation_accepts_either_secret(self):
        body = event()
        assert webhooks.verify_signature(body, sign(body, secret="whsec_new"), secrets=[SECRET, "whsec_new"], now=NOW)

    def test_their_rotation_sends_two_v1_values(self):
        body = event()
        old = sign(body).split("v1=")[1]
        new = sign(body, secret="whsec_new").split("v1=")[1]
        assert webhooks.verify_signature(body, f"t={NOW},v1={new},v1={old}", secrets=[SECRET], now=NOW)

    def test_secret_setting_is_comma_separated(self):
        s = mock.Mock(paybridge_webhook_secret=" whsec_a , whsec_b ,")
        with mock.patch.object(webhooks, "get_settings", return_value=s):
            assert webhooks._secrets() == ["whsec_a", "whsec_b"]


def stored(row_id: int, processed: bool = False) -> list[dict]:
    return [{"id": row_id, "processed_at": "2025-02-19T10:00:00Z" if processed else None}]


def test_first_delivery_is_processed():
    conn = FakeConn(responses=[stored(501), []])
    with mock.patch.object(webhooks.payments, "mark_succeeded") as ms:
        outcome = webhooks.handle_paybridge_event(conn, raw_body=event())
    assert outcome == "processed"
    ms.assert_called_once_with(conn, paybridge_payment_id="pay_123", amount_pence=3600)
    assert "ON CONFLICT (event_id) DO UPDATE" in conn.statements[0][0]
    assert "processed_at = now()" in conn.statements[-1][0]


def test_duplicate_of_processed_event_is_skipped():
    conn = FakeConn(responses=[stored(501, processed=True)])
    with mock.patch.object(webhooks.payments, "mark_succeeded") as ms:
        assert webhooks.handle_paybridge_event(conn, raw_body=event()) == "duplicate"
    ms.assert_not_called()


def test_redelivery_of_failed_event_is_retried():
    """The pre-Nov-2024 bug: a retry of an event whose first processing failed
    used to be dropped as a duplicate. It must be processed again."""
    conn = FakeConn(responses=[stored(501, processed=False), []])
    with mock.patch.object(webhooks.payments, "mark_succeeded") as ms:
        assert webhooks.handle_paybridge_event(conn, raw_body=event()) == "processed"
    ms.assert_called_once()


def test_resent_event_with_new_id_reaches_handler():
    """Dashboard 'Resend' gives a new event id. Dedupe can't help; the
    handler has to be idempotent (payments.mark_succeeded checks status)."""
    conn = FakeConn(responses=[stored(502), []])
    with mock.patch.object(webhooks.payments, "mark_succeeded") as ms:
        webhooks.handle_paybridge_event(conn, raw_body=event(event_id="evt_1_resent"))
    ms.assert_called_once()


def test_handler_failure_keeps_event_for_backlog():
    conn = FakeConn(responses=[stored(503), []])
    with mock.patch.object(webhooks.payments, "mark_succeeded", side_effect=UnknownPayment("no row")):
        assert webhooks.handle_paybridge_event(conn, raw_body=event()) == "failed"
    last_sql, params = conn.statements[-1]
    assert "SET error" in last_sql
    assert "UnknownPayment" in params[0]
    assert ("SAVEPOINT", None) in conn.statements


def test_unknown_event_type_is_stored_and_marked_done():
    conn = FakeConn(responses=[stored(504), []])
    assert webhooks.handle_paybridge_event(conn, raw_body=event(type_="payment.disputed")) == "ignored"


def test_checkout_expired_goes_by_checkout_id():
    conn = FakeConn(responses=[stored(505), []])
    body = json.dumps({"id": "evt_9", "type": "checkout.session.expired", "data": {"object": {"id": "cs_1"}}}).encode()
    with mock.patch.object(webhooks.payments, "expire_checkout") as ex:
        assert webhooks.handle_paybridge_event(conn, raw_body=body) == "processed"
    ex.assert_called_once_with(conn, checkout_id="cs_1")


def test_backlog_dry_run_counts_only():
    rows = [{"id": 1, "payload": json.loads(event())}, {"id": 2, "payload": json.loads(event("evt_2"))}]
    conn = FakeConn(responses=[rows])
    with mock.patch.object(webhooks, "_dispatch") as d:
        assert webhooks.process_unprocessed_events(conn, dry_run=True) == 2
    d.assert_not_called()
