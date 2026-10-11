-- 0006_consents_and_audit.sql
-- Added Nov 2023 after the DPIA review. Consents for marketing / SMS
-- reminders, and an append-only audit log for staff and system actions.

BEGIN;

CREATE TABLE consents (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    resident_id     bigint NOT NULL REFERENCES residents(id),
    purpose         text NOT NULL CHECK (purpose IN ('sms_reminders', 'email_reminders', 'marketing', 'photo')),
    granted         boolean NOT NULL,
    source          text NOT NULL,              -- 'profile_page', 'booking_form', 'sms_stop', 'staff', 'import'
    recorded_at     timestamptz NOT NULL DEFAULT now()
);

-- latest row per (resident, purpose) wins; no row = never asked
CREATE INDEX consents_latest_idx ON consents (resident_id, purpose, recorded_at DESC);

CREATE TABLE audit_log (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at      timestamptz NOT NULL DEFAULT now(),
    actor_type      text NOT NULL DEFAULT 'system' CHECK (actor_type IN ('resident', 'staff', 'system')),
    actor_id        bigint,
    action          text NOT NULL,              -- dotted, e.g. 'booking.cancel', 'refund.manual'
    subject_type    text NOT NULL,              -- usually the table name
    subject_id      bigint,
    detail          jsonb,
    ip_address      inet
);

CREATE INDEX audit_log_subject_idx ON audit_log (subject_type, subject_id);
CREATE INDEX audit_log_created_idx ON audit_log (created_at);

-- Append only. The app role gets INSERT/SELECT, nothing else.
REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM hallpass_app;

COMMIT;
