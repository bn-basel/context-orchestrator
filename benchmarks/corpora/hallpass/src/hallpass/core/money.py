"""Money helpers. All amounts are int pence (ADR 0002).

There is no Money class on purpose; we tried one in 2023 and it made the SQL
boundary annoying. Keep amounts as plain ints named ``*_pence``.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

VAT_RATE_PERCENT = 20


def format_gbp(pence: int) -> str:
    """1234 -> '£12.34', -50 -> '-£0.50'."""
    sign = "-" if pence < 0 else ""
    pounds, rem = divmod(abs(pence), 100)
    return f"{sign}£{pounds:,}.{rem:02d}"


def parse_gbp(text: str) -> int:
    """'12.34', '£12.34', '12' -> pence. Raises ValueError on junk.

    Only used by the staff back office (manual payments, ad-hoc invoice lines).
    """
    cleaned = text.strip().replace("£", "").replace(",", "")
    if not cleaned:
        raise ValueError("empty amount")
    value = Decimal(cleaned)
    if value != value.quantize(Decimal("0.01")):
        raise ValueError(f"more than two decimal places: {text!r}")
    return int((value * 100).to_integral_value())


def percent_of(pence: int, percent: int | Decimal) -> int:
    """Percentage of an amount, rounded half-up to the nearest penny.

    NB: billing's concession code does its own rounding in places (see
    docs/known-issues/billing.md). This is the one we *meant* everyone to use.
    """
    exact = Decimal(pence) * Decimal(percent) / Decimal(100)
    return int(exact.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def pro_rata(pence_per_hour: int, minutes: int) -> int:
    """Price for a duration given an hourly rate, half-up to the penny."""
    exact = Decimal(pence_per_hour) * Decimal(minutes) / Decimal(60)
    return int(exact.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def vat_from_gross(gross_pence: int, rate_percent: int = VAT_RATE_PERCENT) -> int:
    """VAT element of a VAT-inclusive amount (hire prices are quoted gross)."""
    exact = Decimal(gross_pence) * Decimal(rate_percent) / Decimal(100 + rate_percent)
    return int(exact.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def split_evenly(total_pence: int, parts: int) -> list[int]:
    """Split so the parts sum exactly to the total; earlier parts get the extra pennies."""
    if parts <= 0:
        raise ValueError("parts must be positive")
    base, extra = divmod(total_pence, parts)
    return [base + (1 if i < extra else 0) for i in range(parts)]
