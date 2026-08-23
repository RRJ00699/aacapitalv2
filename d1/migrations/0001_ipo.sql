-- 0001_ipo.sql — canonical IPO identity spine.
--
-- Status: CURRENT (Stage A, 5-table target D1 schema)
-- Product contract §6:
--   1. ISIN exact match wins.
--   2. name_norm exact match — fallback.
--   3. symbol / nse_symbol / bse_code MUST NOT be used for identity.
-- name_norm is computed by pipeline/fill_ipo.py:_norm (lowercase, alnum+space,
-- collapse) and MUST match workers/ingest/src/identity.ts:normaliseName.

CREATE TABLE IF NOT EXISTS ipo (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  isin          TEXT    UNIQUE,
  symbol        TEXT,                       -- routing metadata ONLY, never identity
  name_norm     TEXT    NOT NULL,
  name_display  TEXT    NOT NULL,
  sector        TEXT,
  industry      TEXT,
  is_mainboard  INTEGER,                    -- 0 / 1
  status        TEXT,
  listing_date  TEXT,                       -- IST YYYY-MM-DD
  kite_token    INTEGER,                    -- Kite instrument_token (routing, not identity)
  ipomatrix_id  TEXT,
  bse_code      TEXT,
  created_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  updated_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ipo_name_norm_uidx ON ipo(name_norm);
CREATE UNIQUE INDEX IF NOT EXISTS ipo_isin_uidx      ON ipo(isin) WHERE isin IS NOT NULL;
CREATE INDEX        IF NOT EXISTS ipo_status_idx     ON ipo(status);
CREATE INDEX        IF NOT EXISTS ipo_listing_idx    ON ipo(listing_date);
