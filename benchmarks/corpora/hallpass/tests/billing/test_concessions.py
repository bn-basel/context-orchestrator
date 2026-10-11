from __future__ import annotations

from datetime import date

import pytest

from hallpass.billing.concessions import (
    Concession,
    apply_concessions,
    apply_pence_off,
    apply_percent_per_line,
    best_concession,
    discount_pence,
)
from hallpass.billing.pricing import price_slots
from hallpass.core.money import percent_of
from tests.billing.conftest import london, make_rule

TODAY = date(2025, 3, 4)


def pct(code: str, percent: int, until: date | None = None, id: int = 1) -> Concession:
    return Concession(id=id, code=code, percent_off=percent, pence_off=None, valid_until=until)


def fixed(code: str, pence: int, id: int = 9) -> Concession:
    return Concession(id=id, code=code, percent_off=None, pence_off=pence, valid_until=None)


def two_hours(rate: int):
    return price_slots([make_rule(rate=rate)], 10, "resident", london(2025, 3, 4, 10), london(2025, 3, 4, 12))


def test_best_concession_wins_no_stacking():
    cs = [pct("OVER_65", 25, id=1), pct("LEISURE_CARD", 50, id=2)]
    assert best_concession(cs, TODAY, 6000).code == "LEISURE_CARD"


def test_fixed_amount_can_beat_percentage_on_cheap_hire():
    cs = [pct("U18", 30), fixed("STAFF_VOUCHER", 1000)]
    assert best_concession(cs, TODAY, 2000).code == "STAFF_VOUCHER"
    assert best_concession(cs, TODAY, 6000).code == "U18"


def test_expired_concession_ignored():
    assert best_concession([pct("LEISURE_CARD", 50, until=date(2025, 3, 3))], TODAY, 3000) is None


def test_concession_valid_on_its_last_day():
    assert best_concession([pct("U18", 30, until=TODAY)], TODAY, 3000) is not None


def test_even_amount_50_percent():
    out, reasons = apply_concessions(two_hours(3600), [pct("LEISURE_CARD", 50)], TODAY)
    assert out.gross_pence == 3600
    assert reasons == ["LEISURE_CARD concession (50%)"]


def test_odd_half_hour_is_floored_per_line():
    # Documents current behaviour: 1375 * 50% = 687.5 -> 687 on every line.
    lines = apply_percent_per_line(two_hours(2750).lines, 50)
    assert [x.amount_pence for x in lines] == [687, 687, 687, 687]
    assert sum(x.amount_pence for x in lines) == 2748


@pytest.mark.xfail(reason="HP-412: per-line floor vs half-up on the total", strict=True)
def test_concession_total_matches_percent_of_gross():
    q = two_hours(2750)
    out, _ = apply_concessions(q, [pct("LEISURE_CARD", 50)], TODAY)
    assert out.gross_pence == q.gross_pence - percent_of(q.gross_pence, 50)  # 2750 expected, we charge 2748


@pytest.mark.xfail(reason="HP-412", strict=True)
def test_displayed_saving_plus_amount_paid_equals_gross():
    # 1 hour at £27.50 with U18 (30%): lines 1375*70//100 = 962 each -> 1924.
    # "You saved" = 30% of 2750 half-up = 825. 1924 + 825 = 2749. One penny vanishes.
    q = price_slots([make_rule(rate=2750)], 10, "resident", london(2025, 3, 4, 10), london(2025, 3, 4, 11))
    out, _ = apply_concessions(q, [pct("U18", 30)], TODAY)
    assert out.gross_pence + discount_pence(q.gross_pence, 30) == q.gross_pence


def test_block_discount_stacks_after_concession():
    q = price_slots([make_rule(rate=4000)], 10, "resident", london(2025, 3, 4, 10), london(2025, 3, 4, 11))
    out, reasons = apply_concessions(q, [pct("OVER_65", 25)], TODAY, series_occurrences=12)
    # 2000 -> 1500 -> 1350 per line
    assert out.gross_pence == 2700
    assert len(reasons) == 2


def test_block_discount_needs_ten():
    q = price_slots([make_rule(rate=4000)], 10, "resident", london(2025, 3, 4, 10), london(2025, 3, 4, 11))
    out, reasons = apply_concessions(q, [], TODAY, series_occurrences=9)
    assert out.gross_pence == 4000
    assert reasons == []


def test_carer_is_free():
    out, _ = apply_concessions(two_hours(3000), [pct("CARER", 100)], TODAY)
    assert out.gross_pence == 0


def test_pence_off_taken_from_earliest_slots():
    lines = apply_pence_off(two_hours(3000).lines, 2000)
    assert [x.amount_pence for x in lines] == [0, 500, 1500, 1500]


def test_pence_off_never_negative():
    lines = apply_pence_off(two_hours(1000).lines, 5000)
    assert sum(x.amount_pence for x in lines) == 0


def test_bad_percent_rejected():
    with pytest.raises(ValueError):
        apply_percent_per_line([], 120)
