from hallpass.billing.reconciliation import Kind, compare


def pay(id, pb, amount):
    return {"id": id, "paybridge_payment_id": pb, "amount_pence": amount}


def test_clean_day():
    settled = [{"type": "payment", "id": "pay_1", "amount": 3600}]
    assert compare(settled, [pay(1, "pay_1", 3600)], []) == []


def test_penny_difference_is_its_own_kind():
    settled = [{"type": "payment", "id": "pay_1", "amount": 2750}]
    out = compare(settled, [pay(1, "pay_1", 2748)], [])
    assert [e.kind for e in out] == [Kind.PENNY]


def test_real_amount_mismatch():
    settled = [{"type": "payment", "id": "pay_1", "amount": 4800}]
    out = compare(settled, [pay(1, "pay_1", 3600)], [])
    assert out[0].kind is Kind.AMOUNT_MISMATCH


def test_refund_made_in_paybridge_dashboard():
    settled = [{"type": "refund", "id": "re_dash", "amount": -1000}]
    out = compare(settled, [], [])
    assert out[0].kind is Kind.REFUND_UNKNOWN


def test_missing_both_ways():
    settled = [{"type": "payment", "id": "pay_9", "amount": 1000}]
    out = compare(settled, [pay(1, "pay_1", 3600)], [])
    assert {e.kind for e in out} == {Kind.MISSING_LOCALLY, Kind.MISSING_REMOTELY}


def test_refund_stuck_pending():
    settled = [{"type": "refund", "id": "re_1", "amount": -2400}]
    refunds = [{"id": 11, "paybridge_refund_id": "re_1", "status": "submitted"}]
    out = compare(settled, [], refunds)
    assert out[0].kind is Kind.REFUND_STUCK


def test_refund_already_succeeded_is_fine():
    settled = [{"type": "refund", "id": "re_1", "amount": -2400}]
    refunds = [{"id": 11, "paybridge_refund_id": "re_1", "status": "succeeded"}]
    assert compare(settled, [], refunds) == []
