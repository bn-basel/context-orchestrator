-- 0008_thirty_minute_slots.sql
-- ADR 0011 replaces the 15-minute grid with 30 minutes.
--
-- Existing bookings on :15/:45 boundaries were checked before this ran
-- (there were 41, all in the past; finance were happy to leave them). The
-- constraint is added NOT VALID so those historic rows don't block it, then we
-- deliberately never VALIDATE it. If you are reading this because VALIDATE
-- failed: that's why, don't run it.

BEGIN;

ALTER TABLE bookings DROP CONSTRAINT bookings_slot_grid;

ALTER TABLE bookings ADD CONSTRAINT bookings_slot_grid_30 CHECK (
    extract(minute FROM starts_at)::int IN (0, 30)
    AND extract(minute FROM ends_at)::int IN (0, 30)
) NOT VALID;

-- booking_series durations have to line up too
ALTER TABLE booking_series ADD CONSTRAINT booking_series_duration_30
    CHECK (duration_minutes % 30 = 0) NOT VALID;

COMMIT;
