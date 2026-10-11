from __future__ import annotations

from datetime import date, timedelta

import pytest

from hallpass.billing.invoices import build_lines, financial_year
from hallpass.billing.vat import VatTreatment, split_gross, treatment_for
from tests.billing.conftest import london

SCHOOL = {"id": 7, "kind": "school", "charity_number": None}
CHARITY = {"id": 8, "kind": "charity", "charity_number": "1123456"}
UNREGISTERED = {"id": 9, "kind": "charity", "charity_number": None}


def booking(id=1, *, status="confirmed", price=4800, series_id=None, kind="sports_hall", starts=None, cancelled=None, reason=None):
    starts = starts or london(2025, 5, 6, 18)
    return {
        "id": id,
        "series_id": series_id,
        "starts_at": starts,
        "status": status,
        "price_pence": price,
        "cancelled_at": cancelled,
        "cancel_reason": reason,
        "space_name": "Northfield Sports Hall",
        "space_kind": kind,
    }


# --- VAT -------------------------------------------------------------------

@pytest.mark.parametrize(("gross", "vat"), [(1200, 200), (4800, 800), (1375, 229), (1, 0), (0, 0)])
def test_split_gross_standard(gross, vat):
    s = split_gross(gross, VatTreatment.STANDARD)
    assert s.vat_pence == vat
    assert s.net_pence + s.vat_pence == gross


def test_exempt_has_no_vat():
    s = split_gross(4800, VatTreatment.EXEMPT)
    assert (s.net_pence, s.vat_pence) == (4800, 0)


def test_charity_is_exempt():
    # NB this encodes an ASSUMPTION (docs/billing/assumptions-vat.md), not a
    # confirmed rule. If Finance come back and say otherwise, this test is
    # the first thing that should change.
    assert treatment_for(space_kind="meeting_room", organisation=CHARITY, series_occurrences=1) is VatTreatment.EXEMPT


def test_charity_kind_without_number_pays_vat():
    assert treatment_for(space_kind="meeting_room", organisation=UNREGISTERED, series_occurrences=1) is VatTreatment.STANDARD


def test_school_single_let_standard_rated():
    assert treatment_for(space_kind="sports_hall", organisation=SCHOOL, series_occurrences=1) is VatTreatment.STANDARD


def test_series_of_ten_sports_lets_exempt():
    assert treatment_for(space_kind="pitch", organisation=SCHOOL, series_occurrences=10) is VatTreatment.EXEMPT


def test_series_of_ten_meeting_room_still_standard():
    assert treatment_for(space_kind="meeting_room", organisation=SCHOOL, series_occurrences=12) is VatTreatment.STANDARD


# --- invoices --------------------------------------------------------------

@pytest.mark.parametrize(("d", "fy"), [(date(2025, 3, 31), 2024), (date(2025, 4, 1), 2025), (date(2026, 1, 1), 2025)])
def test_financial_year(d, fy):
    assert financial_year(d) == fy


def test_confirmed_booking_one_line_with_vat():
    lines = build_lines([booking()])
    assert len(lines) == 1
    assert lines[0].amount_pence == 4800  # gross; VAT only appears on the PDF
    assert "Tue 06 May 18:00" in lines[0].description


def test_no_show_charged_in_full():
    lines = build_lines([booking(status="no_show")])
    assert lines[0].amount_pence == 4800
    assert lines[0].description.endswith("(no-show)")


def test_late_cancellation_charges_the_non_refundable_part():
    starts = london(2025, 5, 6, 18)
    b = booking(status="cancelled", starts=starts, cancelled=starts - timedelta(days=3), reason="customer")
    lines = build_lines([b])
    assert lines[0].amount_pence == 2400
    assert lines[0].description.startswith("Late cancellation:")


def test_early_cancellation_no_line():
    starts = london(2025, 5, 6, 18)
    b = booking(status="cancelled", starts=starts, cancelled=starts - timedelta(days=10), reason="customer")
    assert build_lines([b]) == []


def test_closure_cancellation_no_line_even_if_late():
    starts = london(2025, 5, 6, 18)
    b = booking(status="cancelled", starts=starts, cancelled=starts - timedelta(hours=2), reason="closure")
    assert build_lines([b]) == []


def test_block_discount_on_ten_in_month():
    rows = [booking(i, series_id=55, kind="meeting_room", starts=london(2025, 5, 1 + i, 18)) for i in range(10)]
    lines = build_lines(rows)
    assert all(x.amount_pence == 4320 for x in lines)


def test_block_straddling_months_misses_discount():
    """HP-377. Six sessions this month, six next month: no discount on either
    invoice even though the series is 12 long. Documenting, not endorsing."""
    rows = [booking(i, series_id=56, starts=london(2025, 5, 20 + i, 18)) for i in range(6)]
    lines = build_lines(rows)
    assert all(x.amount_pence == 4800 for x in lines)
