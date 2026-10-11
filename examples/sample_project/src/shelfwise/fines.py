"""Fine calculation for overdue loans. Amounts are integer cents."""

from __future__ import annotations

from datetime import datetime

from shelfwise.loans import Loan, days_overdue

DAILY_FINE_CENTS = 25


def calculate_fine(loan: Loan, replacement_cost_cents: int, now: datetime) -> int:
    """Fine in cents: 25 cents per overdue day, capped at the replacement cost."""
    days = days_overdue(loan, now)
    return min(days * DAILY_FINE_CENTS, replacement_cost_cents)


def outstanding_fine(fine_cents: int, payments_cents: list[int]) -> int:
    """What is still owed after payments; never negative."""
    return max(fine_cents - sum(payments_cents), 0)
