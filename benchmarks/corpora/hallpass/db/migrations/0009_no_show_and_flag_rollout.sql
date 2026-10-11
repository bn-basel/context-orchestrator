-- 0009_no_show_and_flag_rollout.sql
-- * bookings.status gains 'no_show' (staff mark it from the day sheet)
-- * feature_flags gains a percentage rollout + per-facility allow list
-- * blackout_periods gets a kind so maintenance windows can be told apart
--   from closures in the usage report

BEGIN;

ALTER TABLE bookings DROP CONSTRAINT bookings_status_check;
ALTER TABLE bookings ADD CONSTRAINT bookings_status_check
    CHECK (status IN ('held', 'confirmed', 'cancelled', 'no_show'));

ALTER TABLE bookings ADD COLUMN no_show_marked_by bigint REFERENCES staff_users(id);

-- no_show rows are not in ('held','confirmed') so they drop out of the
-- exclusion constraint. That's intended: a no-show does not block the slot
-- retrospectively, and nobody can book the past anyway.

ALTER TABLE feature_flags
    ADD COLUMN rollout_percent smallint NOT NULL DEFAULT 100
        CHECK (rollout_percent BETWEEN 0 AND 100),
    ADD COLUMN facility_ids bigint[];           -- NULL = all facilities

ALTER TABLE blackout_periods
    ADD COLUMN kind text NOT NULL DEFAULT 'closure'
        CHECK (kind IN ('closure', 'maintenance', 'event', 'weather'));

INSERT INTO feature_flags (key, enabled, description) VALUES
    ('no_show_tracking', true, 'Show the no-show button on the staff day sheet'),
    -- v2 refunds (ADR 0012) went live in 2.1.0 before flags existed; added
    -- here, already on, so finance can fall back to v1 if the tiers misbehave.
    ('refund_policy_v2', true, 'Tiered refunds by notice period (ADR 0012); off = v1 full refund up to 24h')
ON CONFLICT (key) DO NOTHING;

COMMIT;
