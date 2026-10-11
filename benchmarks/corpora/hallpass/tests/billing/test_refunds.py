"""Refund policy tests. The tier boundaries are the bit people get wrong, so
there are a lot of them. Policy: ADR 0012."""

from __future__ import annotations

from datetime import timedelta

import pytest

from hallpass.billing.refunds import Tier, decide
from tests.billing.conftest import london, utc

START = utc(2025, 6, 20, 18)  # Friday evening hire
PRICE = 4800


@pytest.mark.parametrize(
    ("notice", "tier", "amount"),
    [
        (timedelta(days=30), Tier.FULL, 4800),
        (timedelta(days=7), Tier.FULL, 4800),  # exactly 7 days -> full
        (timedelta(days=7) - timedelta(seconds=1), Tier.PARTIAL, 2400),
        (timedelta(hours=48), Tier.PARTIAL, 2400),  # exactly 48h -> partial
        (timedelta(hours=48) - timedelta(seconds=1), Tier.NONE, 0),
        (timedelta(hours=1), Tier.NONE, 0),
        (timedelta(hours=-2), Tier.NONE, 0),  # cancelled after it started (staff tidy-up)
    ],
)
def test_v2_tiers(notice, tier, amount):
    d = decide(PRICE, START, START - notice)
    assert d.tier == tier
    assert d.amount_pence == amount


def test_closure_is_always_full():
    d = decide(PRICE, START, START - timedelta(minutes=30), closure=True)
    assert d.tier == Tier.CLOSURE
    assert d.amount_pence == PRICE


def test_partial_rounds_half_up_on_odd_price():
    # 2748 is what a 50%-concession 2h hire at £27.50/h actually costs (HP-412)
    d = decide(2749, START, START - timedelta(days=3))
    assert d.amount_pence == 1375  # 1374.5 -> 1375


@pytest.mark.parametrize(
    ("notice", "tier"),
    [
        (timedelta(hours=24), Tier.V1_FULL),
        (timedelta(hours=23, minutes=59), Tier.V1_NONE),
        (timedelta(days=10), Tier.V1_FULL),
    ],
)
def test_v1_policy_still_works_behind_flag(notice, tier):
    # ADR 0007 is superseded but the code path exists until we delete the flag.
    d = decide(PRICE, START, START - notice, use_v2=False)
    assert d.tier == tier


def test_seven_days_across_clocks_change_is_168_hours():
    """Documents the known issue: notice is elapsed time, not calendar days.

    Hire on Sat 1 Nov 2025 at 10:00 GMT. Cancelling at 10:00 BST on Sat
    25 Oct (a week earlier on the wall clock) is 169 hours before -> full.
    Sat 28 Mar -> Sat 4 Apr 2026 (clocks go forward in between) is the
    opposite case and the one that generates complaints.
    """
    starts = london(2025, 11, 1, 10)
    assert decide(PRICE, starts, london(2025, 10, 25, 10)).tier == Tier.FULL

    spring_start = london(2026, 4, 4, 10)
    # same wall-clock time a week earlier, but only 167 real hours
    d = decide(PRICE, spring_start, london(2026, 3, 28, 10))
    assert d.notice == timedelta(hours=167)
    assert d.tier == Tier.PARTIAL  # hirer reads the leaflet and expects FULL
