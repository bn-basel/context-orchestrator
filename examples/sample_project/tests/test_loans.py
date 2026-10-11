from datetime import datetime, timezone

import pytest

from shelfwise import AlreadyReturned, LoanLimitExceeded
from shelfwise.loans import LOAN_PERIOD, borrow, return_book

NOW = datetime(2025, 3, 1, 12, 0, tzinfo=timezone.utc)


def test_borrow_sets_due_date():
    loan = borrow(1, member_id=7, book_id=3, active_loans=0, now=NOW)
    assert loan.due_at == NOW + LOAN_PERIOD


def test_borrow_rejects_sixth_loan():
    with pytest.raises(LoanLimitExceeded):
        borrow(1, member_id=7, book_id=3, active_loans=5, now=NOW)


def test_cannot_return_twice():
    loan = return_book(borrow(1, 7, 3, 0, NOW), NOW)
    with pytest.raises(AlreadyReturned):
        return_book(loan, NOW)
