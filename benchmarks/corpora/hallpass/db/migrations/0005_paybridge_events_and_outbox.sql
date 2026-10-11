-- 0005_paybridge_events_and_outbox.sql
-- Raw Paybridge webhook log + the notifications outbox (ADR 0008).

BEGIN;

-- Every webhook we receive is stored before we act on it. event_id is
-- Paybridge's own id; the unique constraint is our dedupe. Only events that
-- passed the signature check get stored at all.
CREATE TABLE paybridge_events (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id        text NOT NULL UNIQUE,
    event_type      text NOT NULL,
    payload         jsonb NOT NULL,
    received_at     timestamptz NOT NULL DEFAULT now(),
    processed_at    timestamptz,
    error           text
);

CREATE INDEX paybridge_events_unprocessed_idx
    ON paybridge_events (received_at) WHERE processed_at IS NULL;

-- kind = template name ('booking_confirmed', 'booking_reminder_24h', ...).
-- dedupe_key stops the same logical message being queued twice (e.g. the
-- reminder job running twice in an hour). It does not stop it being *sent*
-- twice; that's the worker's problem.
CREATE TABLE notifications_outbox (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind                text NOT NULL,
    channel             text NOT NULL CHECK (channel IN ('email', 'sms')),
    recipient           text NOT NULL,
    resident_id         bigint REFERENCES residents(id),
    booking_id          bigint REFERENCES bookings(id),
    payload             jsonb NOT NULL DEFAULT '{}'::jsonb,
    status              text NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'sending', 'sent', 'failed', 'dead', 'cancelled')),
    priority            smallint NOT NULL DEFAULT 5,
    attempts            integer NOT NULL DEFAULT 0,
    next_attempt_at     timestamptz NOT NULL DEFAULT now(),
    claimed_at          timestamptz,
    dedupe_key          text,
    last_error          text,
    provider_message_id text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    sent_at             timestamptz
);

CREATE INDEX notifications_outbox_pending_idx
    ON notifications_outbox (priority, next_attempt_at) WHERE status = 'pending';
CREATE UNIQUE INDEX notifications_outbox_dedupe_idx
    ON notifications_outbox (dedupe_key) WHERE dedupe_key IS NOT NULL;

COMMIT;
