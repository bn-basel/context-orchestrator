-- Shelfwise schema. Money is integer cents (ADR 0004); timestamps are UTC ISO-8601 (ADR 0003).

CREATE TABLE members (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    email       TEXT UNIQUE,
    joined_at   TEXT NOT NULL
);

CREATE TABLE books (
    id                      INTEGER PRIMARY KEY,
    isbn                    TEXT NOT NULL UNIQUE,
    title                   TEXT NOT NULL,
    author                  TEXT NOT NULL,
    replacement_cost_cents  INTEGER NOT NULL CHECK (replacement_cost_cents >= 0)
);

CREATE TABLE loans (
    id           INTEGER PRIMARY KEY,
    member_id    INTEGER NOT NULL REFERENCES members(id),
    book_id      INTEGER NOT NULL REFERENCES books(id),
    borrowed_at  TEXT NOT NULL,
    due_at       TEXT NOT NULL,
    returned_at  TEXT,
    renewals     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE fine_payments (
    id           INTEGER PRIMARY KEY,
    loan_id      INTEGER NOT NULL REFERENCES loans(id),
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    paid_at      TEXT NOT NULL
);

CREATE INDEX loans_member_active ON loans(member_id) WHERE returned_at IS NULL;
