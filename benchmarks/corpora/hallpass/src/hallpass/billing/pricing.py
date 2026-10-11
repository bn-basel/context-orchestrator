"""Work out what a hire costs, before VAT is split out.

A price is built slot by slot. Each 30-minute slot (ADR 0011) is matched
against ``price_rules`` using the slot's *local* start time, because the
tariff sheet Finance gives us is in local time ("evenings are 17:00-22:00")
and nobody wants evening rates to move by an hour in the summer.

price_rules (migration 0004):
    space_id     NULL means "every space of space_kind"
    space_kind   e.g. 'sports_hall'
    hirer_type   resident | club | charity | community_group | school | commercial
    weekday_mask bit 0 = Monday
    local_from / local_to   wall-clock window, local_to defaults to 23:59
    pence_per_hour          GROSS (VAT-inclusive where VAT applies)
    valid_from / valid_to
    priority     higher wins when rules overlap

There is no "peak" column. Peak is just a rule with a higher rate covering
the evening window. Half-hour slots cost half the hourly rate. Rates are
meant to be even so halving is exact -- the back-office form enforces that,
raw SQL does not.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from psycopg import Connection
from psycopg.rows import dict_row

from hallpass.billing.errors import NoPriceRule
from hallpass.core.money import percent_of
from hallpass.core.tz import LONDON

SLOT = timedelta(minutes=30)

HIRER_TYPES = ("resident", "club", "charity", "community_group", "school", "commercial")

# Residents who live outside the borough pay more. The rule sheet only has
# in-borough resident rates; we add this on top. Finance set 25% in 2023.
OUT_OF_BOROUGH_UPLIFT_PERCENT = 25

_DAY_BITS = {0: 1, 1: 2, 2: 4, 3: 8, 4: 16, 5: 32, 6: 64}  # Monday = bit 0


@dataclass(frozen=True, slots=True)
class PriceRule:
    id: int
    space_id: int | None
    space_kind: str | None
    hirer_type: str
    weekday_mask: int
    local_from: time
    local_to: time
    pence_per_hour: int
    valid_from: date
    valid_to: date | None = None
    priority: int = 0

    def covers(self, local_start: datetime) -> bool:
        d = local_start.date()
        if d < self.valid_from or (self.valid_to is not None and d > self.valid_to):
            return False
        if not self.weekday_mask & _DAY_BITS[local_start.weekday()]:
            return False
        # local_to is exclusive. The default 23:59 leaves 23:59-00:00 uncovered,
        # which can't matter on a 30-minute grid. Don't "fix" it to 24:00,
        # Postgres accepts '24:00' for time but Python's time() doesn't.
        return self.local_from <= local_start.time() < self.local_to

    @property
    def half_hour_pence(self) -> int:
        # Odd hourly rates round the half-hour UP. Deliberate (the council never
        # under-charges by accident) but it means four half hours on a £27.51
        # rule cost 2p more than "two hours" on the tariff sheet.
        return (self.pence_per_hour + 1) // 2


@dataclass(frozen=True, slots=True)
class QuoteLine:
    starts_at: datetime  # UTC
    rule_id: int
    amount_pence: int


@dataclass(slots=True)
class Quote:
    space_id: int
    hirer_type: str
    lines: list[QuoteLine] = field(default_factory=list)

    @property
    def gross_pence(self) -> int:
        return sum(line.amount_pence for line in self.lines)

    def by_rule(self) -> dict[int, int]:
        """Totals per price rule -- what the booking summary page lists."""
        out: dict[int, int] = {}
        for line in self.lines:
            out[line.rule_id] = out.get(line.rule_id, 0) + line.amount_pence
        return out


def iter_slots(starts_at: datetime, ends_at: datetime) -> Iterable[datetime]:
    """Yield UTC slot starts. Bookings has already validated the slot grid."""
    if starts_at.tzinfo is None or ends_at.tzinfo is None:
        raise ValueError("naive datetime passed to pricing")
    t = starts_at
    while t < ends_at:
        yield t
        t += SLOT


def pick_rule(rules: Sequence[PriceRule], space_id: int, local_start: datetime) -> PriceRule | None:
    """Space-specific beats kind-wide, then priority, then the newest rule.

    Overlapping rules are normal: Finance add a "summer offer" rule with a
    higher priority on top of the normal ones rather than editing them.
    """
    matches = [r for r in rules if r.covers(local_start)]
    if not matches:
        return None
    matches.sort(key=lambda r: (r.space_id == space_id, r.priority, r.valid_from, r.id), reverse=True)
    return matches[0]


def price_slots(
    rules: Sequence[PriceRule],
    space_id: int,
    hirer_type: str,
    starts_at: datetime,
    ends_at: datetime,
) -> Quote:
    quote = Quote(space_id=space_id, hirer_type=hirer_type)
    for slot_start in iter_slots(starts_at, ends_at):
        local = slot_start.astimezone(LONDON)
        rule = pick_rule(rules, space_id, local)
        if rule is None:
            raise NoPriceRule(space_id, local.strftime("%a %d %b %H:%M"))
        quote.lines.append(QuoteLine(starts_at=slot_start, rule_id=rule.id, amount_pence=rule.half_hour_pence))
    return quote


def load_rules(conn: Connection, space_id: int, hirer_type: str, on: date) -> list[PriceRule]:
    # We load everything valid on the first day and filter per slot. A hire
    # that runs past midnight on the day a rule changes is priced on the old
    # rule throughout. Only the 3G pitch does late hires; nobody has noticed.
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT r.id, r.space_id, r.space_kind, r.hirer_type, r.weekday_mask,
                   r.local_from, r.local_to, r.pence_per_hour, r.valid_from,
                   r.valid_to, r.priority
              FROM price_rules r
              JOIN spaces s ON s.id = %(space_id)s
             WHERE (r.space_id = s.id OR (r.space_id IS NULL AND r.space_kind = s.kind))
               AND r.hirer_type = %(hirer_type)s
               AND r.valid_from <= %(on)s
               AND (r.valid_to IS NULL OR r.valid_to >= %(on)s)
            """,
            {"space_id": space_id, "hirer_type": hirer_type, "on": on},
        )
        return [PriceRule(**row) for row in cur.fetchall()]


def quote(conn: Connection, space_id: int, starts_at: datetime, ends_at: datetime, hirer_type: str = "resident") -> Quote:
    if hirer_type not in HIRER_TYPES:
        raise ValueError(f"unknown hirer_type {hirer_type!r}")
    on = starts_at.astimezone(LONDON).date()
    rules = load_rules(conn, space_id, hirer_type, on)
    return price_slots(rules, space_id, hirer_type, starts_at, ends_at)


def hirer_type_for(organisation: dict | None) -> str:
    """organisations.kind maps 1:1 onto price_rules.hirer_type. Residents
    booking for themselves are 'resident'."""
    if organisation is None:
        return "resident"
    return organisation["kind"]


@dataclass(frozen=True, slots=True)
class PricedHire:
    """What bookings stores. total_pence goes into bookings.price_pence."""

    gross_pence: int  # tariff price, before uplift/concessions
    total_pence: int  # what the hirer pays (VAT-inclusive)
    hirer_type: str
    reasons: tuple[str, ...] = ()


def quote_price(
    conn: Connection,
    *,
    space_id: int,
    starts_at: datetime,
    ends_at: datetime,
    resident_id: int | None,
    organisation_id: int | None,
    series_occurrences: int = 1,
) -> PricedHire:
    """Entry point used by hallpass.bookings (lifecycle + recurring).

    Concessions only apply to residents booking for themselves. An org booking
    made by a member who happens to hold a Leisure Card gets no concession;
    this comes up at the front desk about once a month.

    bookings doesn't pass ``series_occurrences``, so the block-booking discount
    never reaches bookings.price_pence. For organisations it is applied on the
    monthly invoice instead (invoices.py). Residents with a series simply
    don't get it. Not sure anyone has noticed.
    """
    from hallpass.billing.concessions import apply_concessions, load_concessions

    organisation = None
    if organisation_id is not None:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, kind, charity_number FROM organisations WHERE id = %s", (organisation_id,))
            organisation = cur.fetchone()

    hirer_type = hirer_type_for(organisation)
    base = quote(conn, space_id, starts_at, ends_at, hirer_type)
    reasons: list[str] = []

    if organisation is None and resident_id is not None:
        row = conn.execute("SELECT is_in_borough FROM residents WHERE id = %s", (resident_id,)).fetchone()
        lines = base.lines
        if row is not None and not row[0]:
            # Uplift goes on before concessions. Finance confirmed the order in
            # 2023 ("discount off the price they'd actually pay").
            uplift = percent_of(base.gross_pence, OUT_OF_BOROUGH_UPLIFT_PERCENT)
            reasons.append(f"out-of-borough rate (+{OUT_OF_BOROUGH_UPLIFT_PERCENT}%)")
            # Put the whole uplift on the first slot. Ugly, but the lines are
            # only used for concession maths and nobody sees them.
            first = lines[0]
            lines = [QuoteLine(first.starts_at, first.rule_id, first.amount_pence + uplift), *lines[1:]]
        uplifted = Quote(space_id=space_id, hirer_type=hirer_type, lines=list(lines))
        on = starts_at.astimezone(LONDON).date()
        discounted, more = apply_concessions(
            uplifted, load_concessions(conn, resident_id), on, series_occurrences=series_occurrences
        )
        reasons.extend(more)
        total = discounted.gross_pence
    else:
        total = base.gross_pence

    return PricedHire(gross_pence=base.gross_pence, total_pence=total, hirer_type=hirer_type, reasons=tuple(reasons))
