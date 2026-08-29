PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS allowed_users (
  email TEXT PRIMARY KEY,
  added_by TEXT,
  added_at TEXT,
  password_hash TEXT
);

CREATE TABLE IF NOT EXISTS access_requests (
  email TEXT PRIMARY KEY,
  name TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  requested_at TEXT NOT NULL,
  decided_at TEXT,
  decided_by TEXT,
  note TEXT
);
CREATE INDEX IF NOT EXISTS access_requests_status_time ON access_requests(status, requested_at DESC);

CREATE TABLE IF NOT EXISTS user_settings (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_config (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS listing_outcomes (
  ipo_id INTEGER PRIMARY KEY REFERENCES ipo(id),
  listing_open TEXT,
  d1_close TEXT,
  gap_pct TEXT,
  best_close TEXT,
  worst_close TEXT,
  ceiling_20 INTEGER,
  hold_positive_vs_open INTEGER,
  winner_35 INTEGER,
  pool TEXT,
  computed_at TEXT,
  dataset_version TEXT
);

CREATE TABLE IF NOT EXISTS rule_validation_results (
  id INTEGER PRIMARY KEY,
  rule_id TEXT,
  rule_version TEXT,
  backtest_version TEXT,
  dataset TEXT,
  sql_filter TEXT,
  rule_filter TEXT,
  date_range TEXT,
  n INTEGER,
  win_rate TEXT,
  avg_return TEXT,
  median_return TEXT,
  max_drawdown TEXT,
  expectancy TEXT,
  p_vs_baseline TEXT,
  beats_baseline INTEGER,
  baseline_win_rate TEXT,
  universe_n INTEGER,
  run_at TEXT,
  ci95_low TEXT,
  ci95_high TEXT,
  odds_ratio TEXT,
  abs_lift TEXT,
  rel_lift TEXT,
  test_name TEXT,
  q_bh TEXT,
  beats_fdr INTEGER,
  power TEXT,
  git_hash TEXT,
  exclusion_ledger_json TEXT,
  finding_status TEXT
);
CREATE INDEX IF NOT EXISTS rule_validation_rule_lookup ON rule_validation_results(rule_id, run_at DESC);

CREATE TABLE IF NOT EXISTS legacy_insights (
  id INTEGER PRIMARY KEY,
  ipo_id INTEGER REFERENCES ipo(id),
  doc_id INTEGER,
  category TEXT,
  statement TEXT,
  direction TEXT,
  source_type TEXT,
  page_number INTEGER,
  excerpt TEXT,
  model TEXT,
  prompt_version TEXT,
  run_id TEXT,
  confidence TEXT,
  is_current INTEGER,
  created_at TEXT
);
CREATE INDEX IF NOT EXISTS legacy_insights_ipo_current ON legacy_insights(ipo_id, is_current, category);

CREATE TABLE IF NOT EXISTS ipo_news (
  id INTEGER PRIMARY KEY,
  company_name TEXT,
  nse_symbol TEXT,
  publisher TEXT,
  headline TEXT,
  url TEXT,
  published_at TEXT,
  snippet TEXT,
  selection_score INTEGER,
  source TEXT,
  fetch_status TEXT,
  is_current INTEGER,
  created_at TEXT
);
CREATE INDEX IF NOT EXISTS ipo_news_symbol_time ON ipo_news(nse_symbol, published_at DESC);

CREATE TABLE IF NOT EXISTS symbol_aliases (
  old_symbol TEXT PRIMARY KEY,
  new_symbol TEXT NOT NULL,
  note TEXT,
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS legacy_gmp (
  company TEXT NOT NULL,
  d TEXT NOT NULL,
  gmp TEXT,
  est_listing TEXT,
  raw TEXT,
  PRIMARY KEY(company, d)
);
