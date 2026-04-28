-- Helpdesk Utilities — minimal SQLite schema
-- Domain: Italian public water utility (Lombardy), B2C + B2B, ~1M customers in prod.
-- This schema is the demo subset.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS customers (
  id          INTEGER PRIMARY KEY,
  type        TEXT NOT NULL CHECK (type IN ('B2C','B2B')),
  name        TEXT NOT NULL,
  address     TEXT,
  zone        TEXT NOT NULL,
  vat_id      TEXT,
  email       TEXT,
  phone       TEXT,
  vulnerable  INTEGER NOT NULL DEFAULT 0  -- 1 = vulnerable customer flag (forces escalation)
);

CREATE TABLE IF NOT EXISTS invoices (
  id            INTEGER PRIMARY KEY,
  customer_id   INTEGER NOT NULL REFERENCES customers(id),
  period        TEXT NOT NULL,            -- e.g. "2026-Q1"
  amount_eur    REAL NOT NULL,
  status        TEXT NOT NULL CHECK (status IN ('paid','pending','overdue','disputed')),
  issued_date   TEXT NOT NULL,
  due_date      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS switches (
  id              INTEGER PRIMARY KEY,
  customer_id     INTEGER NOT NULL REFERENCES customers(id),
  target_provider TEXT NOT NULL,
  status          TEXT NOT NULL CHECK (status IN ('requested','in_progress','completed','failed','blocked')),
  blocker         TEXT,                   -- e.g. 'unpaid_balance', 'contract_lock', 'address_mismatch'
  opened_at       TEXT NOT NULL,
  closed_at       TEXT
);

CREATE TABLE IF NOT EXISTS tickets (
  id                  INTEGER PRIMARY KEY,
  customer_id         INTEGER NOT NULL REFERENCES customers(id),
  channel             TEXT NOT NULL CHECK (channel IN ('email','phone','chat','web')),
  category            TEXT,               -- assigned by coordinator
  subject             TEXT NOT NULL,
  body                TEXT NOT NULL,
  status              TEXT NOT NULL DEFAULT 'open'
                      CHECK (status IN ('open','agent_handling','escalated','resolved','closed')),
  priority            TEXT NOT NULL DEFAULT 'medium'
                      CHECK (priority IN ('low','medium','high','urgent')),
  opened_at           TEXT NOT NULL,
  closed_at           TEXT,
  agent_handled       INTEGER NOT NULL DEFAULT 0,   -- 1 = handled by agent without human
  confidence          REAL,                          -- coordinator's classification confidence
  escalation_reason   TEXT,
  resolution_summary  TEXT
);

CREATE TABLE IF NOT EXISTS comments (
  id          INTEGER PRIMARY KEY,
  ticket_id   INTEGER NOT NULL REFERENCES tickets(id),
  author      TEXT NOT NULL,              -- 'customer','coordinator','billing_agent','switching_agent','chatbot','human'
  body        TEXT NOT NULL,
  created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kb_articles (
  id      INTEGER PRIMARY KEY,
  title   TEXT NOT NULL,
  body    TEXT NOT NULL,
  tags    TEXT
);

CREATE TABLE IF NOT EXISTS outages (
  id           INTEGER PRIMARY KEY,
  zone         TEXT NOT NULL,
  started_at   TEXT NOT NULL,
  ended_at     TEXT,
  severity     TEXT NOT NULL CHECK (severity IN ('low','medium','high')),
  description  TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
  id          INTEGER PRIMARY KEY,
  ticket_id   INTEGER REFERENCES tickets(id),
  actor       TEXT NOT NULL,
  action      TEXT NOT NULL,
  detail      TEXT,
  ts          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tickets_status   ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_tickets_category ON tickets(category);
CREATE INDEX IF NOT EXISTS idx_tickets_opened   ON tickets(opened_at);
CREATE INDEX IF NOT EXISTS idx_invoices_cust    ON invoices(customer_id);
CREATE INDEX IF NOT EXISTS idx_outages_zone     ON outages(zone);
