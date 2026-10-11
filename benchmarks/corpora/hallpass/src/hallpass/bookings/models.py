from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any

from hallpass.core.errors import ConflictError, HallpassError


class BookingStatus(enum.StrEnum):
    HELD = "held"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


# Statuses that occupy the space. Must match the WHERE clause on the
# bookings_no_overlap exclusion constraint (see ADR 0009) -- if you add a
# status here, add it to the constraint too, or you get double bookings.
ACTIVE_STATUSES: tuple[str, ...] = (BookingStatus.HELD, BookingStatus.CONFIRMED)


class InvalidSlot(HallpassError):
    """Requested times don't sit on the slot grid, or are outside opening hours."""


class BookingConflict(ConflictError):
    """Somebody else has the space (or it's closed). Raised when the exclusion
    constraint fires, or when we spot the clash ourselves first."""

    def __init__(self, message: str, *, space_id: int, starts_at: datetime, ends_at: datetime):
        super().__init__(message)
        self.space_id = space_id
        self.starts_at = starts_at
        self.ends_at = ends_at


class HoldExpired(HallpassError):
    """Tried to confirm a hold that the sweeper already released."""


class IllegalTransition(HallpassError):
    pass


@dataclass(slots=True)
class Booking:
    id: int
    space_id: int
    resident_id: int | None
    organisation_id: int | None
    series_id: int | None
    starts_at: datetime  # UTC, tz-aware
    ends_at: datetime  # UTC, tz-aware
    status: BookingStatus
    price_pence: int
    created_at: datetime
    cancelled_at: datetime | None = None
    hold_expires_at: datetime | None = None
    cancel_reason: str | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Booking":
        return cls(
            id=row["id"],
            space_id=row["space_id"],
            resident_id=row["resident_id"],
            organisation_id=row["organisation_id"],
            series_id=row["series_id"],
            starts_at=row["starts_at"],
            ends_at=row["ends_at"],
            status=BookingStatus(row["status"]),
            price_pence=row["price_pence"],
            created_at=row["created_at"],
            cancelled_at=row.get("cancelled_at"),
            hold_expires_at=row.get("hold_expires_at"),
            cancel_reason=row.get("cancel_reason"),
        )

    @property
    def hirer_kind(self) -> str:
        return "organisation" if self.organisation_id is not None else "resident"

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_STATUSES


@dataclass(slots=True)
class SeriesSpec:
    """What the staff form / org portal sends when asking for a block booking.

    ``start_time`` and ``duration_minutes`` are *local* (Europe/London). We
    keep them local on purpose -- see the DST note in recurring.py.
    """

    space_id: int
    organisation_id: int | None
    resident_id: int | None
    weekday: int  # ISO: Monday == 1 ... Sunday == 7 (matches the DB check). NOT date.weekday()!
    start_time: time
    duration_minutes: int
    first_date: date
    last_date: date
    every_n_weeks: int = 1
    notes: str = ""
    skip_dates: list[date] = field(default_factory=list)


@dataclass(slots=True, frozen=True)
class FreeSlot:
    space_id: int
    starts_at: datetime  # UTC
    ends_at: datetime  # UTC
    # A slot can be "free but waitlistable" -- i.e. it's held by someone
    # whose hold may lapse. The public site shows these greyed out.
    held_by_other: bool = False
