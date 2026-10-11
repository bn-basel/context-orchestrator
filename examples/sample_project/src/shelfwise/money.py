"""Money helpers. All amounts are integer cents (ADR 0004)."""

from __future__ import annotations


def parse_cents(text: str) -> int:
    """Parse '3.50' or '3' into cents. Rejects more than two decimal places."""
    whole, _, frac = text.strip().partition(".")
    if len(frac) > 2:
        raise ValueError(f"too many decimal places: {text!r}")
    return int(whole or "0") * 100 + int(frac.ljust(2, "0") or "0")


def format_cents(amount_cents: int) -> str:
    sign = "-" if amount_cents < 0 else ""
    dollars, cents = divmod(abs(amount_cents), 100)
    return f"{sign}${dollars}.{cents:02d}"
