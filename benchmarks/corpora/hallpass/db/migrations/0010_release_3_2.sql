-- 0010_release_3_2.sql
-- Schema changes for 3.2 (June 2025). Bundled into one file because they
-- went out together; sorry.
--
-- 1. Session invalidation ("sign me out everywhere"): session_epoch on
--    residents and staff_users. Bumping it kills every cookie for that account.
-- 2. Staff sign in with magic links too now, so they need last_login_at.
-- 3. Organisation members are soft-removed so the audit trail still makes sense.
-- 4. Waitlist rework: explicit status instead of the position column. Offers
--    hold a real booking (offer_booking_id) while the resident decides.
-- 5. Blackouts can be withdrawn instead of deleted.
-- 6. Payments: track the Paybridge checkout id and failure codes; a checkout
--    that times out is now 'expired' rather than 'failed'.
-- 7. Refunds record which policy tier (ADR 0012) produced the amount.
-- 8. reconciliation_exceptions for the nightly Paybridge reconciliation.
--
-- Ran in ~40s on prod (the waitlist backfill is the slow bit).

BEGIN;

-- 1, 2
ALTER TABLE residents   ADD COLUMN session_epoch integer NOT NULL DEFAULT 0;
ALTER TABLE staff_users ADD COLUMN session_epoch integer NOT NULL DEFAULT 0,
                        ADD COLUMN last_login_at timestamptz;

-- 3
ALTER TABLE organisation_members ADD COLUMN removed_at timestamptz;

-- 4
ALTER TABLE waitlist_entries
    ADD COLUMN status text NOT NULL DEFAULT 'waiting'
        CHECK (status IN ('waiting', 'offered', 'accepted', 'withdrawn', 'lapsed', 'expired')),
    ADD COLUMN offer_booking_id bigint REFERENCES bookings(id),
    ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now();

UPDATE waitlist_entries SET status = 'expired' WHERE starts_at < now();
UPDATE waitlist_entries SET status = 'offered' WHERE status = 'waiting' AND offered_at IS NOT NULL;

ALTER TABLE waitlist_entries DROP CONSTRAINT waitlist_entries_space_id_starts_at_resident_id_key;
ALTER TABLE waitlist_entries ALTER COLUMN position DROP NOT NULL;   -- unused; drop in a later release
CREATE UNIQUE INDEX waitlist_entries_one_waiting_idx
    ON waitlist_entries (resident_id, space_id, starts_at) WHERE status = 'waiting';

-- 5
ALTER TABLE blackout_periods
    ADD COLUMN withdrawn_at timestamptz,
    ADD COLUMN withdrawn_by_staff_id bigint REFERENCES staff_users(id);

-- 6
ALTER TABLE payments
    ADD COLUMN paybridge_checkout_id text,
    ADD COLUMN failure_code text,
    ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE payments DROP CONSTRAINT payments_status_check;
ALTER TABLE payments ADD CONSTRAINT payments_status_check
    CHECK (status IN ('pending', 'succeeded', 'failed', 'expired', 'refunded', 'partially_refunded'));
CREATE INDEX payments_checkout_idx ON payments (paybridge_checkout_id) WHERE paybridge_checkout_id IS NOT NULL;

-- 7
ALTER TABLE refunds ADD COLUMN policy_tier text;   -- NULL for refunds before v2 policy / manual ones

-- 8
CREATE TABLE reconciliation_exceptions (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    day             date NOT NULL,
    kind            text NOT NULL,
    paybridge_id    text NOT NULL DEFAULT '',
    local_id        bigint,
    detail          jsonb,
    resolved_at     timestamptz,
    resolved_by     bigint REFERENCES staff_users(id),
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (day, kind, paybridge_id)
);

COMMIT;
