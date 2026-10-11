-- 0002_facilities.sql
-- Facilities (buildings / sites) and the spaces inside them.

BEGIN;

CREATE TABLE facilities (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name            text NOT NULL,
    address_line1   text,
    address_line2   text,
    town            text,
    postcode        text,
    timezone        text NOT NULL DEFAULT 'Europe/London',   -- never anything else in practice
    active          boolean NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE spaces (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    facility_id     bigint NOT NULL REFERENCES facilities(id),
    name            text NOT NULL,
    kind            text NOT NULL DEFAULT 'meeting_room'
                    CHECK (kind IN ('sports_hall', 'meeting_room', 'pitch', 'music_room', 'studio')),
    capacity        integer,
    is_bookable     boolean NOT NULL DEFAULT true,
    sort_order      integer NOT NULL DEFAULT 0,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (facility_id, name)
);

-- Opening hours are local wall-clock times. A row per space per weekday.
-- weekday follows ISO: 1 = Monday ... 7 = Sunday.
CREATE TABLE opening_hours (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    space_id    bigint NOT NULL REFERENCES spaces(id) ON DELETE CASCADE,
    weekday     smallint NOT NULL CHECK (weekday BETWEEN 1 AND 7),
    opens_at    time NOT NULL,
    closes_at   time NOT NULL,
    CHECK (closes_at > opens_at),
    UNIQUE (space_id, weekday)
);

-- Closures. space_id NULL means the whole facility is shut.
-- reason is a short code from the staff dropdown, note is free text.
CREATE TABLE blackout_periods (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    facility_id         bigint NOT NULL REFERENCES facilities(id),
    space_id            bigint REFERENCES spaces(id),
    starts_at           timestamptz NOT NULL,
    ends_at             timestamptz NOT NULL,
    reason              text NOT NULL,
    note                text,
    created_by_staff_id bigint REFERENCES staff_users(id),
    created_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (ends_at > starts_at)
);

CREATE INDEX blackout_periods_facility_idx ON blackout_periods (facility_id, starts_at);

COMMIT;
