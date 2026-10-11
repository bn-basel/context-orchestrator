-- 0004_pricing_and_payments.sql
-- Price rules, concessions, invoices, payments and refunds.
-- All money columns are integer pence (ADR 0002). Do not add numeric columns.

BEGIN;

CREATE TABLE price_rules (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    space_id            bigint REFERENCES spaces(id),          -- NULL = applies to all spaces of space_kind
    space_kind          text,
    hirer_type          text NOT NULL,                         -- 'resident' or an organisations.kind
    weekday_mask        smallint NOT NULL DEFAULT 127,         -- bit 0 = Monday
    local_from          time NOT NULL DEFAULT '00:00',
    local_to            time NOT NULL DEFAULT '23:59',
    pence_per_hour      integer NOT NULL CHECK (pence_per_hour >= 0),
    valid_from          date NOT NULL,
    valid_to            date,
    priority            integer NOT NULL DEFAULT 0,
    CHECK (space_id IS NOT NULL OR space_kind IS NOT NULL)
);

CREATE TABLE concessions (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code            text NOT NULL UNIQUE,                       -- e.g. 'LEISURE_CARD', 'U18', 'OVER_65'
    description     text NOT NULL,
    percent_off     integer CHECK (percent_off BETWEEN 0 AND 100),
    pence_off       integer CHECK (pence_off >= 0),
    requires_proof  boolean NOT NULL DEFAULT true,
    active          boolean NOT NULL DEFAULT true,
    CHECK ((percent_off IS NULL) <> (pence_off IS NULL))
);

-- Invoice dates are plain dates (finance think in days, not instants).
CREATE TABLE invoices (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    organisation_id     bigint NOT NULL REFERENCES organisations(id),
    number              text NOT NULL UNIQUE,                   -- 'HP-2324-000123'
    period_start        date NOT NULL,
    issued_on           date,
    due_on              date,
    net_pence           integer NOT NULL DEFAULT 0,
    vat_pence           integer NOT NULL DEFAULT 0,
    total_pence         integer NOT NULL DEFAULT 0,
    status              text NOT NULL DEFAULT 'draft'
                        CHECK (status IN ('draft', 'issued', 'paid', 'void')),
    paid_on             date,
    void_reason         text,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE invoice_lines (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    invoice_id      bigint NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    booking_id      bigint REFERENCES bookings(id),
    description     text NOT NULL,
    net_pence       integer NOT NULL,
    vat_pence       integer NOT NULL DEFAULT 0,
    gross_pence     integer NOT NULL,
    vat_treatment   text NOT NULL DEFAULT 'standard'
);

CREATE TABLE payments (
    id                      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    booking_id              bigint REFERENCES bookings(id),
    invoice_id              bigint REFERENCES invoices(id),
    amount_pence            integer NOT NULL CHECK (amount_pence > 0),
    method                  text NOT NULL DEFAULT 'card' CHECK (method IN ('card', 'bank_transfer', 'cash', 'cheque')),
    paybridge_payment_id    text UNIQUE,
    reference               text,                               -- our checkout ref, or the bank reference
    status                  text NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending', 'succeeded', 'failed', 'refunded', 'partially_refunded')),
    created_at              timestamptz NOT NULL DEFAULT now(),
    CHECK (booking_id IS NOT NULL OR invoice_id IS NOT NULL)
);

CREATE TABLE refunds (
    id                      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payment_id              bigint NOT NULL REFERENCES payments(id),
    amount_pence            integer NOT NULL CHECK (amount_pence > 0),
    reason                  text NOT NULL,
    status                  text NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending', 'succeeded', 'failed')),
    paybridge_refund_id     text UNIQUE,
    requested_by_staff_id   bigint REFERENCES staff_users(id),
    created_at              timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX payments_booking_idx ON payments (booking_id);
CREATE INDEX payments_invoice_idx ON payments (invoice_id);
CREATE INDEX refunds_payment_idx ON refunds (payment_id);

COMMIT;
