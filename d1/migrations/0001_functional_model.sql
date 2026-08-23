PRAGMA foreign_keys = ON;

CREATE TABLE ipo (
  id INTEGER PRIMARY KEY, isin TEXT UNIQUE, name TEXT NOT NULL, name_norm TEXT NOT NULL UNIQUE,
  nse_symbol TEXT, bse_symbol TEXT, ipo_matrix_id INTEGER UNIQUE, security_kind TEXT,
  discovered_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (isin IS NULL OR length(isin)=12)
);
CREATE TABLE ipo_issue (
  ipo_id INTEGER PRIMARY KEY REFERENCES ipo(id), open_date TEXT, close_date TEXT, allotment_date TEXT,
  listing_date TEXT, band_lo_rs REAL, band_hi_rs REAL, issue_price_rs REAL, face_value_rs REAL,
  lot_size_shares INTEGER, issue_size_cr REAL, fresh_cr REAL, ofs_cr REAL, market_cap_cr REAL,
  registrar_name TEXT, brlm_json TEXT, source_name TEXT, source_observed_at TEXT,
  CHECK (band_lo_rs IS NULL OR band_lo_rs>=0), CHECK (band_hi_rs IS NULL OR band_hi_rs>=0),
  CHECK (band_lo_rs IS NULL OR band_hi_rs IS NULL OR band_lo_rs<=band_hi_rs)
);
CREATE TABLE company_profile (
  ipo_id INTEGER PRIMARY KEY REFERENCES ipo(id), business_description TEXT, sector TEXT, industry TEXT,
  incorporated_date TEXT, registered_office TEXT, website TEXT, promoters_json TEXT
);
CREATE TABLE ownership (
  ipo_id INTEGER NOT NULL REFERENCES ipo(id), holder_category TEXT NOT NULL, pre_pct REAL, post_pct REAL,
  dilution_pct REAL, source_fact_id INTEGER, PRIMARY KEY(ipo_id,holder_category),
  CHECK(pre_pct IS NULL OR pre_pct BETWEEN 0 AND 100), CHECK(post_pct IS NULL OR post_pct BETWEEN 0 AND 100)
);
CREATE TABLE objects_of_issue (
  id INTEGER PRIMARY KEY, ipo_id INTEGER NOT NULL REFERENCES ipo(id), row_order INTEGER NOT NULL,
  purpose_code TEXT, purpose_raw TEXT NOT NULL, amount_cr REAL, document_sha256 TEXT, page INTEGER,
  UNIQUE(ipo_id,row_order,document_sha256)
);
CREATE TABLE financial_statements (
  ipo_id INTEGER NOT NULL REFERENCES ipo(id), period TEXT NOT NULL, basis TEXT NOT NULL,
  revenue_cr REAL, total_income_cr REAL, ebitda_cr REAL, pat_cr REAL, net_worth_cr REAL,
  reserves_cr REAL, debt_cr REAL, assets_cr REAL, cash_cr REAL, document_sha256 TEXT, page INTEGER,
  PRIMARY KEY(ipo_id,period,basis)
);
CREATE TABLE fundamental_metrics (
  id INTEGER PRIMARY KEY, ipo_id INTEGER NOT NULL REFERENCES ipo(id), period TEXT, metric_code TEXT NOT NULL,
  value REAL NOT NULL, unit TEXT NOT NULL, method TEXT NOT NULL, calculation_version TEXT,
  document_sha256 TEXT, observed_at TEXT, UNIQUE(ipo_id,period,metric_code,method,observed_at)
);
CREATE TABLE reservations (
  ipo_id INTEGER NOT NULL REFERENCES ipo(id), category TEXT NOT NULL, shares_reserved INTEGER,
  reservation_pct REAL, source_observed_at TEXT, PRIMARY KEY(ipo_id,category)
);
CREATE TABLE subscription_snapshots (
  id INTEGER PRIMARY KEY, ipo_id INTEGER NOT NULL REFERENCES ipo(id), captured_at TEXT NOT NULL,
  category TEXT NOT NULL, shares_reserved INTEGER, shares_bid INTEGER, subscription_x REAL, is_final INTEGER NOT NULL DEFAULT 0,
  observation_fingerprint TEXT NOT NULL UNIQUE, CHECK(is_final IN (0,1))
);
CREATE TABLE anchor_summary (
  ipo_id INTEGER PRIMARY KEY REFERENCES ipo(id), shares INTEGER, amount_cr REAL, investor_count INTEGER,
  allocation_pct REAL, document_sha256 TEXT, observed_at TEXT
);
CREATE TABLE anchor_allocations (
  id INTEGER PRIMARY KEY, ipo_id INTEGER NOT NULL REFERENCES ipo(id), allocation_row INTEGER NOT NULL,
  investor_name_raw TEXT NOT NULL, shares INTEGER, price_rs REAL, amount_cr REAL, allocation_pct REAL,
  document_sha256 TEXT NOT NULL, page INTEGER, derived_class TEXT,
  UNIQUE(document_sha256,allocation_row)
);
CREATE TABLE peer_comparisons (
  id INTEGER PRIMARY KEY, ipo_id INTEGER NOT NULL REFERENCES ipo(id), peer_name_raw TEXT NOT NULL,
  eps_rs REAL, pe_x REAL, pb_x REAL, roe_pct REAL, ronw_pct REAL, market_cap_cr REAL,
  as_of_date TEXT, document_sha256 TEXT, page INTEGER, UNIQUE(ipo_id,peer_name_raw,as_of_date,document_sha256)
);
CREATE TABLE documents (
  sha256 TEXT PRIMARY KEY CHECK(length(sha256)=64), ipo_id INTEGER REFERENCES ipo(id), doc_type TEXT NOT NULL,
  source_url TEXT, size_bytes INTEGER, page_count INTEGER, r2_key TEXT, fetched_at TEXT
);
CREATE TABLE research_findings (
  id INTEGER PRIMARY KEY, ipo_id INTEGER NOT NULL REFERENCES ipo(id), category TEXT NOT NULL, finding_text TEXT NOT NULL,
  direction TEXT, document_sha256 TEXT NOT NULL REFERENCES documents(sha256), page INTEGER,
  evidence_excerpt TEXT NOT NULL, model TEXT, prompt_version TEXT, confidence REAL,
  content_fingerprint TEXT NOT NULL UNIQUE
);
CREATE TABLE gmp_observations (
  id INTEGER PRIMARY KEY, ipo_id INTEGER NOT NULL REFERENCES ipo(id), observed_at TEXT NOT NULL,
  gmp_rs REAL, gmp_pct REAL, source_name TEXT NOT NULL, is_official INTEGER NOT NULL DEFAULT 0,
  observation_fingerprint TEXT NOT NULL UNIQUE, CHECK(is_official=0)
);
CREATE TABLE market_bars (
  ipo_id INTEGER NOT NULL REFERENCES ipo(id), interval TEXT NOT NULL CHECK(interval IN ('1d','15m','5m')),
  ts TEXT NOT NULL, open_rs REAL, high_rs REAL, low_rs REAL, close_rs REAL, volume_shares INTEGER,
  source_name TEXT NOT NULL, content_fingerprint TEXT NOT NULL UNIQUE, PRIMARY KEY(ipo_id,interval,ts)
);
CREATE TABLE listing_observations (
  id INTEGER PRIMARY KEY, ipo_id INTEGER NOT NULL REFERENCES ipo(id), observation_type TEXT NOT NULL,
  observed_at TEXT NOT NULL, price_rs REAL, buy_qty_shares INTEGER, sell_qty_shares INTEGER,
  ieq_shares INTEGER, payload_json TEXT, source_name TEXT NOT NULL, content_fingerprint TEXT NOT NULL UNIQUE
);
CREATE TABLE valuation_runs (
  id INTEGER PRIMARY KEY, ipo_id INTEGER NOT NULL REFERENCES ipo(id), calculated_at TEXT NOT NULL,
  engine_version TEXT NOT NULL, inputs_json TEXT NOT NULL, ratios_json TEXT, peer_median_pe_x REAL,
  fair_value_lo_rs REAL, fair_value_hi_rs REAL, margin_of_safety_pct REAL, missing_inputs_json TEXT,
  run_fingerprint TEXT NOT NULL UNIQUE
);
CREATE TABLE decision_history (
  id INTEGER PRIMARY KEY, ipo_id INTEGER NOT NULL REFERENCES ipo(id), layer TEXT NOT NULL
    CHECK(layer IN ('company_quality','trade_setup','live_action')),
  decided_at TEXT NOT NULL, decision TEXT NOT NULL, engine_version TEXT NOT NULL,
  inputs_json TEXT NOT NULL, evidence_json TEXT, run_fingerprint TEXT NOT NULL UNIQUE
);
CREATE TABLE source_facts (
  id INTEGER PRIMARY KEY, ipo_id INTEGER REFERENCES ipo(id), target_table TEXT NOT NULL, target_field TEXT NOT NULL,
  raw_value TEXT, normalized_value TEXT, unit TEXT, source_name TEXT NOT NULL, document_sha256 TEXT,
  raw_object_sha256 TEXT, observed_at TEXT NOT NULL, parser_version TEXT NOT NULL, confidence REAL,
  observation_fingerprint TEXT NOT NULL UNIQUE
);
CREATE TABLE raw_objects (
  sha256 TEXT PRIMARY KEY CHECK(length(sha256)=64), source_name TEXT NOT NULL, source_object_id TEXT,
  captured_at TEXT, size_bytes INTEGER NOT NULL, payload_json TEXT NOT NULL,
  UNIQUE(source_name,source_object_id,sha256)
);
CREATE TRIGGER raw_objects_no_update BEFORE UPDATE ON raw_objects BEGIN SELECT RAISE(ABORT,'raw_objects is immutable'); END;
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
CREATE INDEX market_bars_lookup ON market_bars(ipo_id,interval,ts);
CREATE INDEX subscription_lookup ON subscription_snapshots(ipo_id,captured_at,category);
CREATE INDEX source_facts_target ON source_facts(ipo_id,target_table,target_field);
