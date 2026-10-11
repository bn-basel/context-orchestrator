from __future__ import annotations

from datetime import date, time

import pytest

from hallpass.billing.errors import NoPriceRule
from hallpass.billing.pricing import hirer_type_for, pick_rule, price_slots
from hallpass.core.tz import LONDON
from tests.billing.conftest import london, make_rule


def test_offpeak_hour_is_two_half_hours(sports_hall_rules):
    q = price_slots(sports_hall_rules, 10, "resident", london(2025, 3, 4, 10), london(2025, 3, 4, 11))
    assert [line.amount_pence for line in q.lines] == [1800, 1800]
    assert q.gross_pence == 3600


def test_booking_straddling_evening_boundary_is_priced_per_slot(sports_hall_rules):
    # Tue 16:00-18:00: one hour day rate, one hour evening rate
    q = price_slots(sports_hall_rules, 10, "resident", london(2025, 3, 4, 16), london(2025, 3, 4, 18))
    assert q.gross_pence == 3600 + 4800
    assert q.by_rule() == {1: 3600, 2: 4800}


def test_weekend_rate(sports_hall_rules):
    q = price_slots(sports_hall_rules, 10, "resident", london(2025, 3, 8, 10), london(2025, 3, 8, 12))
    assert q.gross_pence == 8400


def test_evening_rate_follows_local_time_in_summer(sports_hall_rules):
    # 17:00 BST is 16:00 UTC. Must still be the evening rate.
    q = price_slots(sports_hall_rules, 10, "resident", london(2025, 7, 1, 17), london(2025, 7, 1, 18))
    assert {line.rule_id for line in q.lines} == {2}
    assert q.gross_pence == 4800


def test_clocks_go_back_day_evening_hire(sports_hall_rules):
    # Sunday 26 Oct 2025, clocks went back at 02:00. An 18:00-19:00 hire that
    # evening is two ordinary weekend slots.
    q = price_slots(sports_hall_rules, 10, "resident", london(2025, 10, 26, 18), london(2025, 10, 26, 19))
    assert len(q.lines) == 2
    assert q.gross_pence == 4200


def test_odd_hourly_rate_rounds_half_hour_up():
    assert make_rule(rate=2750).half_hour_pence == 1375
    assert make_rule(rate=2751).half_hour_pence == 1376  # deliberately up, see pricing.py


def test_no_rule_raises_with_local_label(sports_hall_rules):
    with pytest.raises(NoPriceRule) as exc:
        price_slots(sports_hall_rules, 10, "resident", london(2025, 3, 4, 22), london(2025, 3, 4, 23))
    assert "22:00" in exc.value.local_label


def test_higher_priority_rule_wins():
    normal = make_rule(1, rate=3000)
    summer = make_rule(2, rate=2000, valid_from=date(2025, 7, 1), valid_to=date(2025, 8, 31), priority=10)
    assert pick_rule([normal, summer], 10, london(2025, 7, 15, 10).astimezone(LONDON)).id == 2
    assert pick_rule([normal, summer], 10, london(2025, 9, 2, 10).astimezone(LONDON)).id == 1


def test_space_specific_rule_beats_kind_wide_rule():
    kind_wide = make_rule(1, rate=3000, space_id=None, priority=5)
    this_hall = make_rule(2, rate=3400, space_id=10)
    assert pick_rule([kind_wide, this_hall], 10, london(2025, 3, 4, 10).astimezone(LONDON)).id == 2


def test_default_local_to_covers_last_slot():
    late = make_rule(start=time(20, 0), end=time(23, 59), rate=6000)
    assert late.covers(london(2025, 3, 4, 23, 30).astimezone(LONDON))


@pytest.mark.parametrize(
    ("org", "expected"),
    [
        (None, "resident"),
        ({"kind": "charity", "charity_number": "1098765"}, "charity"),
        ({"kind": "club", "charity_number": None}, "club"),
        ({"kind": "commercial", "charity_number": None}, "commercial"),
    ],
)
def test_hirer_type_for(org, expected):
    assert hirer_type_for(org) == expected
