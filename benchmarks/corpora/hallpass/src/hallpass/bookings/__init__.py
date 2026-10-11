"""Bookings and scheduling.

Everything to do with *when* a space can be used and *who* has it:

- ``slots``        -- the 30-minute local-time grid (ADR 0011)
- ``availability`` -- free/busy search used by the public booking pages
- ``lifecycle``    -- hold -> confirm -> cancel / no-show
- ``recurring``    -- block bookings ("series"), materialised as rows (ADR 0005)
- ``waitlist``     -- queue for fully-booked slots, promotion on cancellation
- ``blackouts``    -- closures / maintenance windows
- ``day_sheet``    -- the caretaker's printout
- ``jobs``         -- the bits the worker calls on a schedule

Money is not calculated here; we ask ``hallpass.billing.pricing`` for a quote
and store the result in ``bookings.price_pence``. Refunds are billing's too.
"""

from hallpass.bookings.models import (
    Booking,
    BookingConflict,
    BookingStatus,
    HoldExpired,
    InvalidSlot,
)

__all__ = [
    "Booking",
    "BookingStatus",
    "BookingConflict",
    "HoldExpired",
    "InvalidSlot",
]
