-- 0007_feature_flags.sql
-- ADR 0014. Flags live in the database so staff (well, superusers) can flip
-- them without a deploy.

BEGIN;

CREATE TABLE feature_flags (
    key             text PRIMARY KEY,
    enabled         boolean NOT NULL DEFAULT false,
    description     text NOT NULL,
    updated_by      bigint REFERENCES staff_users(id),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

INSERT INTO feature_flags (key, enabled, description) VALUES
    ('waitlist', false, 'Let residents join a waitlist for a fully booked slot'),
    ('sms_reminders', false, 'Send SMS reminders via TextHub 24h before a booking'),
    ('org_invoicing', true, 'Monthly invoices for organisations that pay by bank transfer'),
    ('paybridge_checkout_v2', false, 'Use Paybridge hosted checkout v2 redirect flow');

COMMIT;
