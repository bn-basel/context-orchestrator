"""The slot grid.

Slots are 30 minutes long (ADR 0011; it used to be 15, ADR 0003) and are
defined in Europe/London wall-clock time. A booking must start and end on a
slot boundary *in local time*. We store UTC in the database, so every check
here converts UTC -> local first.

The awkward cases are the two DST changeover nights. Nothing is open between
01:00 and 02:00 local, so in practice nobody can book into the gap/overlap,
but if someone ever sets 24h opening on a space, ``slots_for_day`` will hit
the spring gap and ``core.tz.local_to_utc`` raises NonExistentLocalTime, which
takes the whole availability search down for that facility. Please don't.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, time, timedelta

from hallpass.bookings.models import InvalidSlot
from hallpass.core.tz import local_to_utc, to_local

SLOT_MINUTES = 30
SLOT = timedelta(minutes=SLOT_MINUTES)

# Bookings longer than this need a staff user (or an organisation account).
MAX_RESIDENT_BOOKING = timedelta(hours=4)
MIN_BOOKING = SLOT

# Some old bookings were made on the 15-minute grid before the switch in
# March 2024 and are still in the table (series that run until 2027, mostly
# Riverside pitches). We don't migrate them -- availability just has to cope
# with a busy period that starts at :15 or :45. See ADR 0011 "Consequences".
LEGACY_SLOT_MINUTES = 15


def is_on_grid(local_dt: datetime, minutes: int = SLOT_MINUTES) -> bool:
    return local_dt.second == 0 and local_dt.microsecond == 0 and local_dt.minute % minutes == 0


def validate_booking_window(
    starts_at: datetime,
    ends_at: datetime,
    *,
    is_staff: bool = False,
    is_organisation: bool = False,
) -> None:
    """Raise InvalidSlot unless [starts_at, ends_at) is a legal booking.

    Both datetimes must be tz-aware. They can be in any zone; we normalise.
    """
    if starts_at.tzinfo is None or ends_at.tzinfo is None:
        raise InvalidSlot("naive datetime passed to validate_booking_window")

    local_start = to_local(starts_at)
    local_end = to_local(ends_at)

    if not is_on_grid(local_start) or not is_on_grid(local_end):
        raise InvalidSlot(
            f"bookings must start and end on the half hour (got {local_start:%H:%M}-{local_end:%H:%M})"
        )

    length = ends_at - starts_at  # real elapsed time, not wall-clock
    if length < MIN_BOOKING:
        raise InvalidSlot("booking is shorter than one slot")
    if length > MAX_RESIDENT_BOOKING and not (is_staff or is_organisation):
        raise InvalidSlot("residents can book at most 4 hours at a time")

    if local_start.date() != local_end.date() and local_end.time() != time(0, 0):
        # Overnight hires are a staff-only thing (the sleepover at Moorfield
        # Community Centre, basically). Staff use the admin screen for those.
        if not is_staff:
            raise InvalidSlot("bookings cannot run past midnight")


def slots_for_day(day: date, opens: time, closes: time) -> Iterator[tuple[datetime, datetime]]:
    """Yield (start_utc, end_utc) for each 30-minute slot between opens and closes
    on ``day`` (a local date).

    Works on wall-clock time and converts each boundary separately, so on the
    day the clocks change you still get 09:00, 09:30, ... local.
    """
    cursor = datetime.combine(day, opens)  # naive local wall-clock
    end = datetime.combine(day, closes)
    if closes == time(0, 0):
        end = datetime.combine(day + timedelta(days=1), time(0, 0))

    while cursor < end:
        nxt = cursor + SLOT
        yield (
            local_to_utc(cursor.date(), cursor.time()),
            local_to_utc(nxt.date(), nxt.time()),
        )
        cursor = nxt


def snap_down(local_dt: datetime) -> datetime:
    """Round a local datetime down to the slot grid."""
    minute = (local_dt.minute // SLOT_MINUTES) * SLOT_MINUTES
    return local_dt.replace(minute=minute, second=0, microsecond=0)


def snap_up(local_dt: datetime) -> datetime:
    down = snap_down(local_dt)
    if down == local_dt:
        return down
    return (down.replace(tzinfo=None) + SLOT).replace(tzinfo=local_dt.tzinfo)


def slot_count(starts_at: datetime, ends_at: datetime) -> int:
    """Number of grid slots a booking covers. Used by pricing for per-slot rates.

    Uses *wall-clock* difference, so a 01:00-03:00 booking on the night the
    clocks go forward counts as 4 slots even though only an hour passes. The
    billing team said that's fine, nobody's going to book that.
    """
    local_start = to_local(starts_at).replace(tzinfo=None)
    local_end = to_local(ends_at).replace(tzinfo=None)
    minutes = int((local_end - local_start).total_seconds() // 60)
    return max(0, minutes // SLOT_MINUTES)
