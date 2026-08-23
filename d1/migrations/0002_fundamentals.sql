-- 0002_fundamentals.sql — one authoritative row per IPO.
--
-- Status: CURRENT (Stage A, 5-table target D1 schema)
-- Consolidates Neon `ipo_issue`, latest `subscription_snapshots`,
-- latest `financial_statements`, latest `valuation`, latest `decisions`,
-- and `listing_outcomes` into a single row keyed by ipo_id.
--
-- Precision model (see d1/CONVENTIONS.md §1): every rupee / ratio field is
-- stored as a TEXT decimal string. SQL never adds or averages them; the
-- only allowed SQL comparison uses CAST(x AS REAL) in CHECK constraints.

CREATE TABLE IF NOT EXISTS fundamentals (
  ipo_id                    INTEGER PRIMARY KEY REFERENCES ipo(id) ON DELETE RESTRICT,

  -- Issue window
  open_date                 TEXT,
  close_date                TEXT,
  allotment_date            TEXT,

  -- Price band / issue
  band_lo                   TEXT,
  band_hi                   TEXT,
  issue_price               TEXT,
  face_value                TEXT,
  lot_size                  INTEGER,

  -- Sizing
  issue_size_cr             TEXT,
  fresh_cr                  TEXT,
  ofs_cr                    TEXT,
  market_cap_cr             TEXT,

  -- Ownership / structure
  promoter_holding_pre      TEXT,
  promoter_holding_post     TEXT,
  registrar                 TEXT,
  brlm_count                INTEGER,
  allocation_qib_pct        TEXT,
  allocation_nii_pct        TEXT,
  allocation_retail_pct     TEXT,

  -- Financials (latest FY / restated)
  revenue                   TEXT,
  total_income              TEXT,
  ebitda                    TEXT,
  pat                       TEXT,
  net_worth                 TEXT,
  total_debt                TEXT,
  total_assets              TEXT,
  eps_pre                   TEXT,
  eps_post                  TEXT,
  roe                       TEXT,
  roce                      TEXT,
  ronw                      TEXT,
  debt_equity               TEXT,
  pat_margin                TEXT,
  ebitda_margin             TEXT,
  rev_cagr_3y               TEXT,

  -- History of the above two blocks; minimal JSON array by (period,basis).
  financial_history_json    TEXT,

  -- Valuation (latest run)
  ipo_pe                    TEXT,
  pe_pre                    TEXT,
  pe_post                   TEXT,
  pb                        TEXT,
  peer_median_pe            TEXT,
  fair_value                TEXT,
  margin_of_safety_pct      TEXT,
  valuation_score           TEXT,
  valuation_band            TEXT,

  -- Subscription / anchor (latest final)
  qib_x                     TEXT,
  nii_x                     TEXT,
  bnii_x                    TEXT,
  snii_x                    TEXT,
  retail_x                  TEXT,
  total_x                   TEXT,
  anchor_amount_cr          TEXT,
  anchor_count              INTEGER,

  -- Listing outcome (day-1)
  listing_open              TEXT,
  d1_close                  TEXT,
  gap_pct                   TEXT,

  -- Current verdicts
  fundamental_verdict       TEXT,
  listing_action            TEXT,

  engine_version            TEXT,
  computed_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  updated_at                TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),

  -- Product contract §6: WEAK fundamentals cannot be paired with a BUY action.
  CHECK (
    fundamental_verdict IS NULL
    OR listing_action IS NULL
    OR NOT (upper(fundamental_verdict)='WEAK' AND upper(listing_action) LIKE 'BUY%')
  ),
  -- band_lo <= band_hi (only allowed CAST-to-REAL comparison, per CONVENTIONS §1)
  CHECK (
    band_lo IS NULL OR band_hi IS NULL OR CAST(band_lo AS REAL) <= CAST(band_hi AS REAL)
  ),
  -- band_lo <= issue_price
  CHECK (
    issue_price IS NULL OR band_lo IS NULL OR CAST(band_lo AS REAL) <= CAST(issue_price AS REAL)
  ),
  -- issue_price <= band_hi
  CHECK (
    issue_price IS NULL OR band_hi IS NULL OR CAST(issue_price AS REAL) <= CAST(band_hi AS REAL)
  )
);

CREATE INDEX IF NOT EXISTS fund_verdict_idx      ON fundamentals(fundamental_verdict);
CREATE INDEX IF NOT EXISTS fund_listing_open_idx ON fundamentals(open_date);
