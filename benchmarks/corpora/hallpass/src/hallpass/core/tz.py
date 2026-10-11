"""Europe/London helpers.

Storage is UTC (timestamptz). Slots, opening hours and anything a human types
or reads are local wall-clock time. These helpers are the only conversion
points; please don't sprinkle ZoneInfo(...) around the codebase.

DST notes, because we keep relearning them:
  * Spring forward (last Sunday in March): 01:00-01:59 local does not exist.
    ``local_to_utc`` raises NonExistentLocalTime for those.
  * Fall back (last Sunday in October): 01:00-01:59 local happens twice.
    We pick the *first* occurrence (fold=0) unless told otherwise. Facilities
    are closed at that hour anyway, so in practice this only bites the
    worker's 'tomorrow' calculations and recurring series (see
    docs/known-issues/bookings.md).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")


class NonExistentLocalTime(ValueError):
    pass


def to_local(instant: datetime) -> datetime:
    if instant.tzinfo is None:
        raise ValueError("naive datetime passed to to_local; storage values must be aware")
    return instant.astimezone(LONDON)


def to_utc(dt: datetime) -> datetime:
    """Aware datetime (any zone) -> UTC. Refuses naive input."""
    if dt.tzinfo is None:
        raise ValueError("naive datetime passed to to_utc")
    return dt.astimezone(UTC)


def local_to_utc(day: date, wall: time, *, fold: int = 0) -> datetime:
    """Combine a local date and wall-clock time and return the UTC instant."""
    local = datetime.combine(day, wall, tzinfo=LONDON).replace(fold=fold)
    # Round-trip check catches the spring-forward gap: a non-existent time
    # comes back shifted by an hour.
    back = local.astimezone(UTC).astimezone(LONDON)
    if (back.hour, back.minute) != (wall.hour, wall.minute):
        raise NonExistentLocalTime(f"{day} {wall} does not exist in Europe/London")
    return local.astimezone(UTC)


def local_day_bounds(day: date) -> tuple[datetime, datetime]:
    """UTC [start, end) of a local calendar day. 23h or 25h on DST days."""
    start = datetime.combine(day, time(0), tzinfo=LONDON).astimezone(UTC)
    end = datetime.combine(day + timedelta(days=1), time(0), tzinfo=LONDON).astimezone(UTC)
    return start, end


def is_dst_change_day(day: date) -> bool:
    start, end = local_day_bounds(day)
    return (end - start) != timedelta(hours=24)


def format_local(instant: datetime, fmt: str = "%a %d %b %Y, %H:%M") -> str:
    """For emails/SMS/UI. e.g. 'Tue 14 Oct 2025, 18:30'."""
    return to_local(instant).strftime(fmt)
