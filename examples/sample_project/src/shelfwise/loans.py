"""Loan lifecycle: borrowing, returning, renewing and overdue days."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from shelfwise import AlreadyReturned, LoanLimitExceeded

LOAN_PERIOD = timedelta(days=21)
MAX_ACTIVE_LOANS = 5  # assumption, see docs/assumptions.md


@dataclass(frozen=True)
class Loan:
    id: int
    member_id: int
    book_id: int
    borrowed_at: datetime
    due_at: datetime
    returned_at: datetime | None = None
    renewals: int = 0


def borrow(loan_id: int, member_id: int, book_id: int, active_loans: int, now: datetime) -> Loan:
    if active_loans >= MAX_ACTIVE_LOANS:
        raise LoanLimitExceeded(f"member {member_id} already has {active_loans} active loans")
    return Loan(loan_id, member_id, book_id, borrowed_at=now, due_at=now + LOAN_PERIOD)


def days_overdue(loan: Loan, now: datetime) -> int:
    """Whole days between the due timestamp and the return (or now).

    Known issue BUG-12: ceil() charges a partial day as a full day.
    """
    end = loan.returned_at or now
    if end <= loan.due_at:
        return 0
    return math.ceil((end - loan.due_at).total_seconds() / 86400)


def return_book(loan: Loan, now: datetime) -> Loan:
    if loan.returned_at is not None:
        raise AlreadyReturned(f"loan {loan.id} was returned at {loan.returned_at}")
    return replace(loan, returned_at=now)


def renew(loan: Loan, now: datetime) -> Loan:
    """Extend the due date by one loan period from now.

    Known issue BUG-15: does not record a fine that has already accrued.
    """
    return replace(loan, due_at=now + LOAN_PERIOD, renewals=loan.renewals + 1)
