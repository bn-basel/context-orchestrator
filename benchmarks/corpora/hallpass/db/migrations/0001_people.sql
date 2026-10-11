-- 0001_people.sql
-- Residents, organisations and staff. Initial schema, Sept 2023.

BEGIN;

CREATE EXTENSION IF NOT EXISTS citext;

-- A resident row is created the first time someone asks for a magic link, so
-- almost everything except email is nullable. verified_at is set the first
-- time they actually click the link.
CREATE TABLE residents (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email           citext NOT NULL UNIQUE,
    display_name    text,
    mobile          text,                       -- E.164, normalised in app
    postcode        text,                       -- used for in-borough pricing
    is_in_borough   boolean NOT NULL DEFAULT false,
    created_at      timestamptz NOT NULL DEFAULT now(),
    verified_at     timestamptz,
    last_login_at   timestamptz,
    anonymised_at   timestamptz                 -- set by the retention job (ADR 0010)
);

CREATE TABLE organisations (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name                text NOT NULL,
    kind                text NOT NULL CHECK (kind IN ('club', 'charity', 'community_group', 'school', 'commercial')),
    charity_number      text,
    invoice_email       citext,
    invoice_address     text,
    on_account          boolean NOT NULL DEFAULT false,   -- pays by monthly invoice / bank transfer
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE organisation_members (
    organisation_id bigint NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    resident_id     bigint NOT NULL REFERENCES residents(id),
    role            text NOT NULL CHECK (role IN ('member', 'admin')),   -- 'admin' = org admin
    added_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (organisation_id, resident_id)
);

CREATE TABLE staff_users (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email       citext NOT NULL UNIQUE,
    full_name   text,
    role        text NOT NULL CHECK (role IN ('facility_staff', 'finance', 'superuser')),
    created_at  timestamptz NOT NULL DEFAULT now(),
    disabled_at timestamptz
);

COMMIT;
