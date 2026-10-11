from datetime import datetime, timezone

from shelfwise.fines import calculate_fine, outstanding_fine
from shelfwise.loans import Loan

UTC = timezone.utc
DUE = datetime(2025, 3, 1, 23, 59, 59, tzinfo=UTC)


def make_loan(returned_at=None):
    return Loan(1, 1, 1, borrowed_at=datetime(2025, 2, 8, tzinfo=UTC), due_at=DUE,
                returned_at=returned_at)


def test_no_fine_when_returned_on_time():
    assert calculate_fine(make_loan(DUE), replacement_cost_cents=2000, now=DUE) == 0


def test_fine_is_25_cents_per_day():
    returned = datetime(2025, 3, 4, 23, 59, 59, tzinfo=UTC)
    assert calculate_fine(make_loan(returned), replacement_cost_cents=2000, now=returned) == 75


def test_fine_is_capped_at_replacement_cost():
    returned = datetime(2025, 6, 1, tzinfo=UTC)
    assert calculate_fine(make_loan(returned), replacement_cost_cents=500, now=returned) == 500


def test_outstanding_fine_never_negative():
    assert outstanding_fine(100, [60, 60]) == 0
