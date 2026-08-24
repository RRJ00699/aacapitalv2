PRAGMA foreign_keys = ON;

CREATE TABLE ipo (
  id INTEGER PRIMARY KEY, isin TEXT UNIQUE, name TEXT NOT NULL, name_norm TEXT NOT NULL UNIQUE,
  -- Multiple NULL ISINs are intentional before allotment; SQLite UNIQUE permits them.
  nse_symbol TEXT, bse_symbol TEXT, ipo_matrix_id INTEGER UNIQUE,
  security_kind TEXT NOT NULL DEFAULT 'EQUITY' CHECK(security_kind IN ('EQUITY','REIT','INVIT','FPO')),
  status TEXT NOT NULL DEFAULT 'ANNOUNCED'
    CHECK(status IN ('ANNOUNCED','UPCOMING','OPEN','CLOSED','ALLOTTED','LISTED','WITHDRAWN')),
  discovered_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (isin IS NULL OR length(isin)=12)
);
CREATE TABLE ipo_issue (
  ipo_id INTEGER PRIMARY KEY REFERENCES ipo(id), open_date TEXT, close_date TEXT, allotment_date TEXT,
  listing_date TEXT,
  lock30_date TEXT GENERATED ALWAYS AS (CASE WHEN listing_date IS NULL THEN NULL ELSE date(listing_date,'+30 days') END) STORED,
  lock90_date TEXT GENERATED ALWAYS AS (CASE WHEN listing_date IS NULL THEN NULL ELSE date(listing_date,'+90 days') END) STORED,
  is_book_built INTEGER NOT NULL DEFAULT 1 CHECK(is_book_built IN (0,1)),
  band_lo_rs TEXT, band_hi_rs TEXT, issue_price_rs TEXT, face_value_rs TEXT,
  lot_size_shares INTEGER, issue_size_cr TEXT, fresh_cr TEXT, ofs_cr TEXT, market_cap_cr TEXT,
  registrar_name TEXT, brlm_json TEXT, source_name TEXT, source_observed_at TEXT,
  CHECK (band_lo_rs IS NULL OR CAST(band_lo_rs AS NUMERIC)>=0),
  CHECK (band_hi_rs IS NULL OR CAST(band_hi_rs AS NUMERIC)>=0),
  CHECK (band_lo_rs IS NULL OR band_hi_rs IS NULL OR CAST(band_lo_rs AS NUMERIC)<=CAST(band_hi_rs AS NUMERIC)),
  CHECK (issue_price_rs IS NULL OR band_lo_rs IS NULL OR CAST(issue_price_rs AS NUMERIC)>=CAST(band_lo_rs AS NUMERIC)),
  CHECK (issue_price_rs IS NULL OR band_hi_rs IS NULL OR CAST(issue_price_rs AS NUMERIC)<=CAST(band_hi_rs AS NUMERIC)),
  CHECK (is_book_built=0 OR band_lo_rs IS NULL OR face_value_rs IS NULL OR CAST(band_lo_rs AS NUMERIC)>=CAST(face_value_rs AS NUMERIC))
);
CREATE TABLE company_profile (
  ipo_id INTEGER PRIMARY KEY REFERENCES ipo(id), business_description TEXT, sector TEXT, industry TEXT,
  incorporated_date TEXT, registered_office TEXT, website TEXT, promoters_json TEXT
);
CREATE TABLE ownership (
  ipo_id INTEGER NOT NULL REFERENCES ipo(id), holder_category TEXT NOT NULL, pre_pct TEXT, post_pct TEXT,
  dilution_pct TEXT, source_fact_id INTEGER, PRIMARY KEY(ipo_id,holder_category),
  CHECK(pre_pct IS NULL OR CAST(pre_pct AS NUMERIC) BETWEEN 0 AND 100),
  CHECK(post_pct IS NULL OR CAST(post_pct AS NUMERIC) BETWEEN 0 AND 100)
);
CREATE TABLE objects_of_issue (
  id INTEGER PRIMARY KEY, ipo_id INTEGER NOT NULL REFERENCES ipo(id), row_order INTEGER NOT NULL,
  purpose_code TEXT, purpose_raw TEXT NOT NULL, amount_cr TEXT, document_sha256 TEXT, page INTEGER,
  UNIQUE(ipo_id,row_order,document_sha256)
);
CREATE TABLE financial_statements (
  ipo_id INTEGER NOT NULL REFERENCES ipo(id), period TEXT NOT NULL, basis TEXT NOT NULL,
  revenue_cr TEXT, total_income_cr TEXT, ebitda_cr TEXT, pat_cr TEXT, net_worth_cr TEXT,
  reserves_cr TEXT, debt_cr TEXT, assets_cr TEXT, cash_cr TEXT, document_sha256 TEXT, page INTEGER,
  PRIMARY KEY(ipo_id,period,basis)
);
CREATE TABLE reservations (
  ipo_id INTEGER NOT NULL REFERENCES ipo(id), category TEXT NOT NULL, shares_reserved INTEGER,
  reservation_pct TEXT, source_observed_at TEXT, PRIMARY KEY(ipo_id,category)
);
CREATE TABLE subscription_snapshots (
  id INTEGER PRIMARY KEY, ipo_id INTEGER NOT NULL REFERENCES ipo(id), captured_at TEXT NOT NULL,
  category TEXT NOT NULL, shares_reserved INTEGER, shares_bid INTEGER, subscription_x TEXT, is_final INTEGER NOT NULL DEFAULT 0,
  observation_fingerprint TEXT NOT NULL UNIQUE, CHECK(is_final IN (0,1))
);
CREATE TABLE anchor_summary (
  ipo_id INTEGER PRIMARY KEY REFERENCES ipo(id), shares INTEGER, amount_cr TEXT, investor_count INTEGER,
  allocation_pct TEXT, document_sha256 TEXT, observed_at TEXT
);
CREATE TABLE anchor_allocations (
  id INTEGER PRIMARY KEY, ipo_id INTEGER NOT NULL REFERENCES ipo(id), allocation_row INTEGER NOT NULL,
  investor_name_raw TEXT NOT NULL, shares INTEGER, price_rs TEXT, amount_cr TEXT, allocation_pct TEXT,
  document_sha256 TEXT NOT NULL, page INTEGER, derived_class TEXT,
  UNIQUE(document_sha256,allocation_row)
);
CREATE TABLE peer_comparisons (
  id INTEGER PRIMARY KEY, ipo_id INTEGER NOT NULL REFERENCES ipo(id), peer_name_raw TEXT NOT NULL,
  eps_rs TEXT, pe_x TEXT, pb_x TEXT, roe_pct TEXT, ronw_pct TEXT, market_cap_cr TEXT,
  as_of_date TEXT, document_sha256 TEXT, page INTEGER, UNIQUE(ipo_id,peer_name_raw,as_of_date,document_sha256)
);
CREATE TABLE documents (
  sha256 TEXT PRIMARY KEY CHECK(length(sha256)=64), ipo_id INTEGER REFERENCES ipo(id), doc_type TEXT NOT NULL,
  source_url TEXT, size_bytes INTEGER, page_count INTEGER, r2_key TEXT, fetched_at TEXT
);
CREATE TABLE research_findings (
  id INTEGER PRIMARY KEY, ipo_id INTEGER NOT NULL REFERENCES ipo(id), category TEXT NOT NULL, finding_text TEXT NOT NULL,
  direction TEXT, document_sha256 TEXT NOT NULL REFERENCES documents(sha256), page INTEGER,
  evidence_excerpt TEXT NOT NULL, model TEXT, prompt_version TEXT, confidence TEXT,
  content_fingerprint TEXT NOT NULL UNIQUE
);
CREATE TABLE gmp_observations (
  id INTEGER PRIMARY KEY, ipo_id INTEGER NOT NULL REFERENCES ipo(id), observed_at TEXT NOT NULL,
  gmp_rs TEXT, gmp_pct TEXT, source_name TEXT NOT NULL, is_official INTEGER NOT NULL DEFAULT 0,
  observation_fingerprint TEXT NOT NULL UNIQUE, CHECK(is_official=0)
);
CREATE TABLE market_bars (
  ipo_id INTEGER NOT NULL REFERENCES ipo(id), interval TEXT NOT NULL CHECK(interval IN ('1d','15m','5m')),
  ts TEXT NOT NULL, open_rs TEXT, high_rs TEXT, low_rs TEXT, close_rs TEXT, volume_shares INTEGER,
  source_name TEXT NOT NULL, content_fingerprint TEXT NOT NULL UNIQUE, PRIMARY KEY(ipo_id,interval,ts)
);
CREATE TABLE listing_observations (
  id INTEGER PRIMARY KEY, ipo_id INTEGER NOT NULL REFERENCES ipo(id), observation_type TEXT NOT NULL,
  observed_at TEXT NOT NULL, price_rs TEXT, buy_qty_shares INTEGER, sell_qty_shares INTEGER,
  ieq_shares INTEGER, payload_json TEXT, source_name TEXT NOT NULL, content_fingerprint TEXT NOT NULL UNIQUE
);
CREATE TABLE valuation_runs (
  id INTEGER PRIMARY KEY, ipo_id INTEGER NOT NULL REFERENCES ipo(id), calculated_at TEXT NOT NULL,
  engine_version TEXT NOT NULL, inputs_json TEXT NOT NULL, ratios_json TEXT, peer_median_pe_x TEXT,
  fair_value_lo_rs TEXT, fair_value_hi_rs TEXT, margin_of_safety_pct TEXT, missing_inputs_json TEXT,
  run_fingerprint TEXT NOT NULL UNIQUE
);
CREATE TABLE decision_history (
  id INTEGER PRIMARY KEY, ipo_id INTEGER NOT NULL REFERENCES ipo(id), layer TEXT NOT NULL
    CHECK(layer IN ('company_quality','trade_setup','live_action')),
  decided_at TEXT NOT NULL, decision TEXT NOT NULL, engine_version TEXT NOT NULL,
  inputs_json TEXT NOT NULL, evidence_json TEXT, run_fingerprint TEXT NOT NULL UNIQUE
);
CREATE TRIGGER decision_history_no_update BEFORE UPDATE ON decision_history
WHEN NOT (OLD.id IS NEW.id AND OLD.ipo_id IS NEW.ipo_id AND OLD.layer IS NEW.layer
  AND OLD.decided_at IS NEW.decided_at AND OLD.decision IS NEW.decision
  AND OLD.engine_version IS NEW.engine_version AND OLD.inputs_json IS NEW.inputs_json
  AND OLD.evidence_json IS NEW.evidence_json AND OLD.run_fingerprint IS NEW.run_fingerprint)
BEGIN SELECT RAISE(ABORT,'decision_history is append-only'); END;
CREATE TRIGGER decision_history_no_delete BEFORE DELETE ON decision_history BEGIN SELECT RAISE(ABORT,'decision_history is append-only'); END;
CREATE TABLE source_facts (
  id INTEGER PRIMARY KEY, ipo_id INTEGER REFERENCES ipo(id), target_table TEXT NOT NULL, target_field TEXT NOT NULL,
  raw_value TEXT, normalized_value TEXT, unit TEXT, source_name TEXT NOT NULL, document_sha256 TEXT,
  raw_object_sha256 TEXT, observed_at TEXT NOT NULL, parser_version TEXT NOT NULL, confidence TEXT,
  observation_fingerprint TEXT NOT NULL UNIQUE
);
CREATE TABLE raw_objects (
  sha256 TEXT PRIMARY KEY CHECK(length(sha256)=64), source_name TEXT NOT NULL, source_object_id TEXT,
  captured_at TEXT, size_bytes INTEGER NOT NULL, payload_json TEXT NOT NULL,
  UNIQUE(source_name,source_object_id,sha256)
);
CREATE TRIGGER raw_objects_no_update BEFORE UPDATE ON raw_objects
WHEN NOT (OLD.sha256 IS NEW.sha256 AND OLD.source_name IS NEW.source_name
  AND OLD.source_object_id IS NEW.source_object_id AND OLD.captured_at IS NEW.captured_at
  AND OLD.size_bytes IS NEW.size_bytes AND OLD.payload_json IS NEW.payload_json)
BEGIN SELECT RAISE(ABORT,'raw_objects is immutable'); END;
CREATE TRIGGER raw_objects_no_delete BEFORE DELETE ON raw_objects BEGIN SELECT RAISE(ABORT,'raw_objects is immutable'); END;
CREATE TABLE migration_quarantine (
  id INTEGER PRIMARY KEY, source_name TEXT NOT NULL, source_identity TEXT, dataset TEXT NOT NULL,
  reason_code TEXT NOT NULL, detail_json TEXT NOT NULL, raw_sha256 TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fingerprint TEXT NOT NULL UNIQUE
);
CREATE TABLE migration_checkpoints (
  dataset TEXT PRIMARY KEY, last_key TEXT, source_rows INTEGER NOT NULL DEFAULT 0,
  written_rows INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
-- Derived lifecycle contract: 0 means NOT_DUE, never missing/failed/zero.
CREATE VIEW ipo_lifecycle_due AS
SELECT id AS ipo_id, status,
  CASE WHEN status='WITHDRAWN' THEN 0 ELSE 1 END AS issue_due,
  CASE WHEN status IN ('UPCOMING','OPEN','CLOSED','ALLOTTED','LISTED') THEN 1 ELSE 0 END AS documents_due,
  CASE WHEN status IN ('CLOSED','ALLOTTED','LISTED') THEN 1 ELSE 0 END AS subscription_due,
  CASE WHEN status IN ('ALLOTTED','LISTED') THEN 1 ELSE 0 END AS allotment_due,
  CASE WHEN status='LISTED' THEN 1 ELSE 0 END AS market_due
FROM ipo;
CREATE INDEX market_bars_lookup ON market_bars(ipo_id,interval,ts);
CREATE INDEX subscription_lookup ON subscription_snapshots(ipo_id,captured_at,category);
CREATE INDEX source_facts_target ON source_facts(ipo_id,target_table,target_field);
CREATE UNIQUE INDEX ipo_nse_symbol_unique ON ipo(nse_symbol) WHERE nse_symbol IS NOT NULL;
