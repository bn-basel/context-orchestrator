"""Concessions (resident discounts) and the block-booking discount.

Two different things live here, and people mix them up constantly:

* A *concession* belongs to a person: Leisure Card holder, under-18, over-65,
  registered disabled. The catalogue is the ``concessions`` table (code,
  percent_off OR pence_off). Which residents hold which concession is in
  ``resident_concessions`` (added later, migration "resident concessions";
  ask platform if you can't find it). Staff check the evidence at the front
  desk and set valid_until; we just read the result. Only the single best
  concession applies -- they do NOT stack (Finance, 2023).

* The *block-booking discount* belongs to a series: 10% off for 10 or more
  sessions in one series. It DOES stack with a concession, applied after it.
  For organisations it's applied on the invoice, see invoices.py.

Rounding: see ``apply_percent_per_line``. Known issue, see
docs/known-issues/billing.md ("Concession rounding on odd amounts").
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date

from psycopg import Connection
from psycopg.rows import dict_row

from hallpass.billing.pricing import Quote, QuoteLine

BLOCK_DISCOUNT_PERCENT = 10
BLOCK_DISCOUNT_MIN_OCCURRENCES = 10

# The codes in production as of 2025. Kept here for the tests and the
# back-office dropdown order; the table is the source of truth.
KNOWN_CODES = ("LEISURE_CARD", "U18", "OVER_65", "DISABILITY", "CARER", "STAFF_VOUCHER")


@dataclass(frozen=True, slots=True)
class Concession:
    id: int
    code: str
    percent_off: int | None
    pence_off: int | None
    valid_until: date | None

    def is_valid(self, on: date) -> bool:
        return self.valid_until is None or on <= self.valid_until

    def saving_on(self, gross_pence: int) -> int:
        """Approximate saving, only used to choose the best concession."""
        if self.percent_off is not None:
            return gross_pence * self.percent_off // 100
        return min(self.pence_off or 0, gross_pence)

    @property
    def label(self) -> str:
        if self.percent_off is not None:
            return f"{self.code} concession ({self.percent_off}%)"
        return f"{self.code} (£{(self.pence_off or 0) / 100:.2f} off)"  # display only, not money maths


def best_concession(concessions: Sequence[Concession], on: date, gross_pence: int) -> Concession | None:
    valid = [c for c in concessions if c.is_valid(on)]
    if not valid:
        return None
    return max(valid, key=lambda c: (c.saving_on(gross_pence), c.id))


def load_concessions(conn: Connection, resident_id: int) -> list[Concession]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT c.id, c.code, c.percent_off, c.pence_off, rc.valid_until
              FROM resident_concessions rc
              JOIN concessions c ON c.id = rc.concession_id
             WHERE rc.resident_id = %s
               AND rc.revoked_at IS NULL
               AND c.active
            """,
            (resident_id,),
        )
        return [Concession(**r) for r in cur.fetchall()]


def apply_percent_per_line(lines: Sequence[QuoteLine], percent_off: int) -> list[QuoteLine]:
    """Discount each half-hour line individually.

    NOTE on rounding. This uses integer floor division per line, so a 50% cut
    on a 1,375p half hour gives 687p, not 687.5 -> 688 (half-up, which is what
    ADR 0002 and core.money.percent_of do). Over a 2-hour hire that's 4 lines
    and the hirer pays 2p less than "half price". The income report, the
    refund code and the "You saved" figure all work on the *total* with
    half-up rounding, so the numbers disagree by a penny or two.

    Not fixed because changing it changes bookings.price_pence for future
    bookings already held/confirmed at the old price, and the invoice lines
    for orgs. HP-412. Finance said in April 2025 that 1-2p is "not material"
    but would like it fixed "at some point".
    """
    if not 0 <= percent_off <= 100:
        raise ValueError(f"percent_off out of range: {percent_off}")
    keep = 100 - percent_off
    return [replace(line, amount_pence=line.amount_pence * keep // 100) for line in lines]


def apply_pence_off(lines: Sequence[QuoteLine], pence_off: int) -> list[QuoteLine]:
    """Fixed amount off the booking, taken from the earliest slots first."""
    out: list[QuoteLine] = []
    left = pence_off
    for line in lines:
        take = min(left, line.amount_pence)
        left -= take
        out.append(replace(line, amount_pence=line.amount_pence - take))
    return out


def discount_pence(gross: int, percent_off: int) -> int:
    """The discount on a total, rounded half-up. Display only.

    The checkout page shows "You saved £x.xx" using this, which is why a
    customer can see a saving that is 1p different from gross minus what they
    actually paid. Yes, really. HP-412 again.
    """
    return (gross * percent_off + 50) // 100


def apply_concessions(
    quote: Quote,
    concessions: Sequence[Concession],
    on: date,
    *,
    series_occurrences: int = 1,
) -> tuple[Quote, list[str]]:
    """Return a discounted copy of the quote and human-readable reasons."""
    reasons: list[str] = []
    lines = list(quote.lines)

    best = best_concession(concessions, on, quote.gross_pence)
    if best is not None:
        if best.percent_off:
            lines = apply_percent_per_line(lines, best.percent_off)
        elif best.pence_off:
            lines = apply_pence_off(lines, best.pence_off)
        reasons.append(best.label)

    if series_occurrences >= BLOCK_DISCOUNT_MIN_OCCURRENCES:
        lines = apply_percent_per_line(lines, BLOCK_DISCOUNT_PERCENT)
        reasons.append(f"block booking discount ({BLOCK_DISCOUNT_PERCENT}%)")

    return Quote(space_id=quote.space_id, hirer_type=quote.hirer_type, lines=lines), reasons
