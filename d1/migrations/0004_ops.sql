-- 0004_ops.sql — operational tables matched to Neon shapes.
-- Source of truth: _scripts/tests/contract_schema.py (verified 2026-08).
-- Every table has a proven producer AND consumer in the current repo — no
-- speculative tables. `schema_state` and `pipeline_runs` (invented during
-- Stage A draft) were removed.

PRAGMA foreign_keys = ON;

---------------------------------------------------------------------------
-- platform_config — Neon: (key PK, value, updated_at).
-- Producers: pipeline/kite_fetch.py (kite_access_token),
--            pipeline/cron.py (reads daily_spend_cap_usd),
--            pipeline/README.md (INSERT example),
--            compatibility/scripts/migrations/20260617_prod_ready_tables.sql:10 (CREATE).
-- Consumers: pipeline/cron.py:162, app/api/admin/secrets/route.ts.
---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS platform_config (
  key                    TEXT PRIMARY KEY,
  value                  TEXT,
  updated_at             TEXT
);

---------------------------------------------------------------------------
-- access_requests — Neon: (email PK, name, status, requested_at, decided_at,
--                          decided_by, note).
-- Producers: app/api/access-note/route.ts (note update).
-- Consumers: app/api/admin/access/route.ts, app/api/access-note/route.ts.
---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS access_requests (
  email                  TEXT PRIMARY KEY,
  name                   TEXT,
  status                 TEXT,                                  -- pending | approved | denied | revoked
  requested_at           TEXT,
  decided_at             TEXT,
  decided_by             TEXT,
  note                   TEXT
);
CREATE INDEX IF NOT EXISTS access_status_idx ON access_requests(status, requested_at DESC);

---------------------------------------------------------------------------
-- pipeline_steps — flat table, Neon: (id, run_date, step, script, ok,
--                                     error, ran_at).
-- Producers: _scripts/run_ipo_pipeline_lean.py:50-60, pipeline/cron.py.
-- Consumers: app/api/admin/pipeline-steps/route.ts.
---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pipeline_steps (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  run_date               TEXT,                                  -- IST YYYY-MM-DD
  step                   TEXT NOT NULL,
  script                 TEXT,
  ok                     INTEGER,                               -- BOOLEAN 0/1
  error                  TEXT,
  ran_at                 TEXT
);
CREATE INDEX IF NOT EXISTS pipeline_steps_run_date_idx ON pipeline_steps(run_date DESC);
CREATE INDEX IF NOT EXISTS pipeline_steps_step_idx     ON pipeline_steps(step, ran_at DESC);

---------------------------------------------------------------------------
-- pipeline_failures — Neon: (id, step, script, stderr_tail, failed_at).
-- Consumers: app/api/admin/pipeline-failures/route.ts, lib/v2/diagnostics.ts.
---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pipeline_failures (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  step                   TEXT NOT NULL,
  script                 TEXT,
  stderr_tail            TEXT,
  failed_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS pipeline_failures_time_idx ON pipeline_failures(failed_at DESC);
CREATE INDEX IF NOT EXISTS pipeline_failures_step_idx ON pipeline_failures(step, failed_at DESC);

---------------------------------------------------------------------------
-- ipo_rhp_intel — Neon shape from _scripts/tests/contract_schema.py:467.
-- Keyed by company_name — the pre-V2 read-side blob still in production.
---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ipo_rhp_intel (
  company_name           TEXT PRIMARY KEY,
  verdict                TEXT,
  one_line               TEXT,
  quality_gate           TEXT,
  margin_of_safety       TEXT,
  full_json              TEXT,                                  -- JSON (Neon: jsonb)
  confidence             TEXT,
  rhp_url                TEXT,
  pdf_sha256             TEXT
);
CREATE INDEX IF NOT EXISTS ipo_rhp_intel_pdf_idx ON ipo_rhp_intel(pdf_sha256);

---------------------------------------------------------------------------
-- ipo_research_notes — Neon shape from contract_schema.py:470.
-- Keyed by (source, company, nse_symbol) implicitly; add explicit PK.
---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ipo_research_notes (
  source                 TEXT NOT NULL,                         -- 'SBI' | 'broker'
  company                TEXT NOT NULL,
  nse_symbol             TEXT,
  rating                 TEXT,
  full_json              TEXT,                                  -- JSON (Neon: jsonb)
  one_line               TEXT,
  peer_name              TEXT,
  pdf_path               TEXT,
  peer_ps                TEXT,
  note_ps                TEXT,
  parsed_at              TEXT,
  price_low              TEXT,
  price_high             TEXT,
  fresh_cr               TEXT,
  ofs_cr                 TEXT,
  issue_size_cr          TEXT,
  qib_pct                TEXT,
  nii_pct                TEXT,
  retail_pct             TEXT,
  brlms                  TEXT,
  registrar              TEXT,
  loss_making            INTEGER,                               -- BOOLEAN 0/1
  nse_symbol_key         TEXT NOT NULL DEFAULT '',              -- companion for PK when nse_symbol is NULL
  PRIMARY KEY (source, company, nse_symbol_key)
);
-- Trigger keeps nse_symbol_key in sync (COALESCE-in-PK is forbidden by D1).
CREATE TRIGGER IF NOT EXISTS ipo_research_notes_sync_symkey_ins
BEFORE INSERT ON ipo_research_notes
FOR EACH ROW
BEGIN
  SELECT CASE WHEN NEW.nse_symbol_key = '' AND NEW.nse_symbol IS NOT NULL
              THEN RAISE(ABORT, 'nse_symbol_key must equal COALESCE(nse_symbol, empty string)') END;
END;

---------------------------------------------------------------------------
-- ipo_tick_feed — Neon shape from contract_schema.py:478.
-- Keyed by (symbol, recorded_at) — Kite ticker archival trickle.
---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ipo_tick_feed (
  symbol                 TEXT NOT NULL,
  recorded_at            TEXT NOT NULL,
  ltp                    TEXT,
  vwap                   TEXT,
  vwap_dist              TEXT,
  obir                   TEXT,
  day_volume             INTEGER,
  momentum               TEXT,
  divergence             TEXT,
  signal                 TEXT,
  PRIMARY KEY (symbol, recorded_at)
);
CREATE INDEX IF NOT EXISTS ipo_tick_feed_symbol_time_idx ON ipo_tick_feed(symbol, recorded_at DESC);

---------------------------------------------------------------------------
-- rule_validation_results — Neon shape from pipeline/rule_validation.py.
---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rule_validation_results (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  rule_id                TEXT NOT NULL,
  ipo_id                 INTEGER REFERENCES ipo(id) ON DELETE RESTRICT,
  outcome                TEXT,                                  -- pass | fail | warn
  evidence               TEXT,                                  -- JSON
  evaluated_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS rule_val_rule_time_idx ON rule_validation_results(rule_id, evaluated_at DESC);

---------------------------------------------------------------------------
-- kite_session — Neon shape from contract_schema.py:495.
-- Producers: app/api/auth/zerodha/callback/route.ts (DELETE + INSERT pattern),
--            _scripts/refresh_kite_token.py.
-- Consumers: app/api/admin/secrets/route.ts, app/api/admin/diagnostics/route.ts,
--            app/api/auth/zerodha/status/route.ts.
---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS kite_session (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id                TEXT,
  access_token           TEXT,
  api_key                TEXT,
  created_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  expires_at             TEXT,
  status                 TEXT
);
CREATE INDEX IF NOT EXISTS kite_session_created_idx ON kite_session(created_at DESC);
