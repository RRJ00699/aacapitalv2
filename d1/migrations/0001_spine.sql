-- 0001_spine.sql — V2 spine, matched exactly to Neon shape
-- (source of truth: pipeline/conftest.py `V2_DDL`, verified against
-- pipeline/fill_v2.py, pipeline/fill_ipo.py writer INSERTs).
--
-- Precision policy (see d1/CONVENTIONS.md):
--   D1/SQLite has no DECIMAL. Every field that is NUMERIC in Neon is stored
--   in D1 as TEXT holding a decimal string (up to 6 dp). TEXT is the SINGLE
--   canonical representation. No paired paise/bp integer columns exist;
--   sorting in SQL is not required by the current pipeline/read paths
--   (snapshot builder sorts in application code). Reconciliation compares
--   TEXT byte-for-byte after normalisation.

PRAGMA foreign_keys = ON;

---------------------------------------------------------------------------
-- ipo — one row per company/issue. `id` is a BIGINT surrogate, matching
-- pipeline/conftest.py:30. ISIN, symbol, kite_token are DISPLAY/identity-
-- lookup columns; NEVER used as PK.
---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ipo (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,   -- Neon: BIGINT; D1 uses INTEGER (same domain, 64-bit)
  isin                   TEXT UNIQUE,
  symbol                 TEXT,                                 -- NSE symbol; DISPLAY only, never identity
  name_norm              TEXT NOT NULL,                        -- identity fallback: EXACT match only
  name_display           TEXT NOT NULL,
  sector                 TEXT,
  industry               TEXT,
  is_mainboard           INTEGER,                              -- BOOLEAN as 0/1 (Neon: BOOLEAN)
  status                 TEXT,                                 -- upstream string set (values enumerated by pipeline)
  listing_date           TEXT,                                 -- IST YYYY-MM-DD (Neon: DATE)
  kite_token             INTEGER,                              -- Kite instrument token; DISPLAY/lookup only
  ipomatrix_id           TEXT,
  bse_code               TEXT,
  in_backtest_universe   INTEGER,                              -- BOOLEAN
  created_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  updated_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
-- Prevent two rows carrying the same normalised name (identity invariant).
CREATE UNIQUE INDEX IF NOT EXISTS ipo_name_norm_uidx ON ipo(name_norm);
CREATE INDEX IF NOT EXISTS ipo_status_idx    ON ipo(status);
CREATE INDEX IF NOT EXISTS ipo_listing_idx   ON ipo(listing_date);
CREATE INDEX IF NOT EXISTS ipo_symbol_idx    ON ipo(symbol);

---------------------------------------------------------------------------
-- ipo_issue — issue economics. Column names/types are Neon's.
-- Rupee amounts (band_lo, band_hi, issue_price, face_value, fresh_cr,
-- ofs_cr, issue_size_cr) are TEXT decimal.
---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ipo_issue (
  ipo_id                 INTEGER PRIMARY KEY REFERENCES ipo(id) ON DELETE RESTRICT,
  open_date              TEXT,
  close_date             TEXT,
  allotment_date         TEXT,
  band_lo                TEXT,
  band_hi                TEXT,
  issue_price            TEXT,
  lot_size               INTEGER,
  face_value             TEXT,
  fresh_cr               TEXT,
  ofs_cr                 TEXT,
  issue_size_cr          TEXT,
  registrar              TEXT,
  brlm_count             INTEGER,
  updated_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),

  -- Cross-field sanity (all values are decimal strings; CAST to REAL only
  -- for the ordering comparison, which is fine because we don't store the
  -- REAL — the canonical TEXT is untouched).
  CHECK ( band_lo IS NULL OR band_hi IS NULL
          OR CAST(band_lo AS REAL) <= CAST(band_hi AS REAL) ),
  CHECK ( issue_price IS NULL OR band_lo IS NULL
          OR CAST(band_lo AS REAL) <= CAST(issue_price AS REAL) ),
  CHECK ( issue_price IS NULL OR band_hi IS NULL
          OR CAST(issue_price AS REAL) <= CAST(band_hi AS REAL) )
);

---------------------------------------------------------------------------
-- subscription_snapshots — full Neon shape
---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS subscription_snapshots (
  ipo_id                 INTEGER NOT NULL REFERENCES ipo(id) ON DELETE RESTRICT,
  captured_at            TEXT NOT NULL,                        -- UTC ISO-8601
  is_final               INTEGER,                              -- BOOLEAN 0/1
  qib_x                  TEXT,
  nii_x                  TEXT,
  bnii_x                 TEXT,
  snii_x                 TEXT,
  retail_x               TEXT,
  total_x                TEXT,
  anchor_amount_cr       TEXT,
  anchor_count           INTEGER,
  applications_lakh      TEXT,
  mf_shares_bid          TEXT,
  mf_pct_qib             TEXT,
  PRIMARY KEY (ipo_id, captured_at)
);
CREATE INDEX IF NOT EXISTS subs_time_idx ON subscription_snapshots(ipo_id, captured_at DESC);

---------------------------------------------------------------------------
-- financial_statements — Neon shape: (ipo_id, period, basis)
---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS financial_statements (
  ipo_id                 INTEGER NOT NULL REFERENCES ipo(id) ON DELETE RESTRICT,
  period                 TEXT NOT NULL,                        -- e.g. FY23 / FY24 / 9M-FY25
  basis                  TEXT NOT NULL,                        -- e.g. consolidated / standalone / restated
  revenue                TEXT,
  total_income           TEXT,
  ebitda                 TEXT,
  pat                    TEXT,
  net_worth              TEXT,
  total_debt             TEXT,
  total_assets           TEXT,
  source                 TEXT,
  fetched_at             TEXT,
  PRIMARY KEY (ipo_id, period, basis)
);

---------------------------------------------------------------------------
-- documents — minimal V2 shape (sha256 PK, ipo_id, doc_type)
---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documents (
  sha256                 TEXT PRIMARY KEY,
  ipo_id                 INTEGER REFERENCES ipo(id) ON DELETE RESTRICT,
  doc_type               TEXT NOT NULL                          -- 'rhp' | 'drhp' | 'sbi_note' | 'anchor' | 'other'
);
CREATE INDEX IF NOT EXISTS documents_ipo_idx   ON documents(ipo_id);
CREATE INDEX IF NOT EXISTS documents_type_idx  ON documents(doc_type);

---------------------------------------------------------------------------
-- source_facts — Neon shape (matches pipeline/conftest.py:73).
-- Simple current-value ledger. Idempotency across retries is enforced by
-- a composite unique key on (ipo_id, field, source, fetched_at) — a re-run
-- with the same instant is a no-op via ON CONFLICT ignoring; new fetched_at
-- values are new observations. Retries within the same second do NOT create
-- duplicate rows.
---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS source_facts (
  ipo_id                 INTEGER NOT NULL REFERENCES ipo(id) ON DELETE RESTRICT,
  field                  TEXT NOT NULL,                         -- e.g. 'ipo_issue.issue_price'
  value                  TEXT,
  source                 TEXT NOT NULL,                         -- 'nse' | 'sebi' | 'sbi' | 'kite' | 'ipomatrix' | 'derived' | 'manual'
  doc_id                 TEXT,                                  -- optional: documents.sha256
  confidence             TEXT,                                  -- 0..1 as decimal string, optional
  fetched_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  PRIMARY KEY (ipo_id, field, source, fetched_at)
);
CREATE INDEX IF NOT EXISTS source_facts_field_idx  ON source_facts(ipo_id, field, fetched_at DESC);
CREATE INDEX IF NOT EXISTS source_facts_source_idx ON source_facts(source, fetched_at DESC);
