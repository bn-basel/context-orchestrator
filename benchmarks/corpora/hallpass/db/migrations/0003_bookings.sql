-- 0003_bookings.sql
-- Bookings, recurring series and the waitlist.
--
-- The exclusion constraint is the thing that actually stops double bookings
-- (ADR 0009). The application-level availability check is only there to give
-- a nice error message; if two requests race, Postgres wins.

BEGIN;

CREATE EXTENSION IF NOT EXISTS btree_gist;

-- A series is the *template*; each occurrence is materialised as its own
-- bookings row (ADR 0005). local_start_time is wall-clock Europe/London.
CREATE TABLE booking_series (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    space_id            bigint NOT NULL REFERENCES spaces(id),
    resident_id         bigint REFERENCES residents(id),
    organisation_id     bigint REFERENCES organisations(id),
    weekday             smallint NOT NULL CHECK (weekday BETWEEN 1 AND 7),
    local_start_time    time NOT NULL,
    duration_minutes    integer NOT NULL CHECK (duration_minutes > 0),
    first_date          date NOT NULL,
    last_date           date NOT NULL,
    every_n_weeks       smallint NOT NULL DEFAULT 1 CHECK (every_n_weeks BETWEEN 1 AND 4),
    notes               text,
    created_by_staff_id bigint REFERENCES staff_users(id),
    created_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (resident_id IS NOT NULL OR organisation_id IS NOT NULL),
    CHECK (last_date >= first_date)
);

CREATE TABLE bookings (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    space_id            bigint NOT NULL REFERENCES spaces(id),
    resident_id         bigint REFERENCES residents(id),
    organisation_id     bigint REFERENCES organisations(id),
    series_id           bigint REFERENCES booking_series(id),
    starts_at           timestamptz NOT NULL,
    ends_at             timestamptz NOT NULL,
    status              text NOT NULL DEFAULT 'held'
                        CHECK (status IN ('held', 'confirmed', 'cancelled')),
    price_pence         integer NOT NULL DEFAULT 0 CHECK (price_pence >= 0),
    hold_expires_at     timestamptz,
    created_by_staff_id bigint REFERENCES staff_users(id),   -- NULL = booked online by the hirer
    created_at          timestamptz NOT NULL DEFAULT now(),
    cancelled_at        timestamptz,
    cancel_reason       text,
    CHECK (ends_at > starts_at),
    CHECK (resident_id IS NOT NULL OR organisation_id IS NOT NULL),
    -- 15 minute grid (ADR 0003). Replaced in 0008.
    CONSTRAINT bookings_slot_grid CHECK (
        extract(minute FROM starts_at)::int % 15 = 0
        AND extract(minute FROM ends_at)::int % 15 = 0
    ),
    CONSTRAINT bookings_no_overlap EXCLUDE USING gist (
        space_id WITH =,
        tstzrange(starts_at, ends_at, '[)') WITH &&
    ) WHERE (status IN ('held', 'confirmed'))
);

CREATE INDEX bookings_resident_idx ON bookings (resident_id, starts_at DESC);
CREATE INDEX bookings_org_idx ON bookings (organisation_id, starts_at DESC);
CREATE INDEX bookings_series_idx ON bookings (series_id) WHERE series_id IS NOT NULL;
CREATE INDEX bookings_hold_expiry_idx ON bookings (hold_expires_at) WHERE status = 'held';

-- First version of the waitlist: plain FIFO by position. Reworked in 0010.
CREATE TABLE waitlist_entries (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    space_id        bigint NOT NULL REFERENCES spaces(id),
    resident_id     bigint NOT NULL REFERENCES residents(id),
    starts_at       timestamptz NOT NULL,
    ends_at         timestamptz NOT NULL,
    position        integer NOT NULL,
    offered_at      timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (space_id, starts_at, resident_id)
);

COMMIT;
