PRAGMA foreign_keys = ON;

-- One row per orchestrated production run.  The run detail is intentionally compact;
-- per-lane evidence belongs in pipeline_events below.
CREATE TABLE IF NOT EXISTS pipeline_runs (
  id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  mode TEXT NOT NULL CHECK(mode IN ('live','dry-run')),
  status TEXT NOT NULL CHECK(status IN ('running','ok','partial','failed')),
  orchestrator_version TEXT NOT NULL,
  selected_ipos INTEGER NOT NULL DEFAULT 0,
  paid_cost_usd TEXT NOT NULL DEFAULT '0',
  summary_json TEXT
);

CREATE TABLE IF NOT EXISTS pipeline_events (
  id INTEGER PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES pipeline_runs(id),
  lane TEXT NOT NULL,
  ipo_id INTEGER REFERENCES ipo(id),
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL CHECK(status IN ('running','ok','skipped','partial','failed')),
  counts_json TEXT,
  detail_json TEXT,
  event_fingerprint TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS pipeline_events_run_lane ON pipeline_events(run_id,lane,ipo_id);

-- Paid extraction completion/idempotency ledger.  The full normalized model output is
-- retained here; source-backed facts are additionally routed to their canonical tables.
CREATE TABLE IF NOT EXISTS extraction_runs (
  id INTEGER PRIMARY KEY,
  ipo_id INTEGER NOT NULL REFERENCES ipo(id),
  document_sha256 TEXT NOT NULL REFERENCES documents(sha256),
  source_type TEXT NOT NULL CHECK(source_type IN ('RHP','SBI')),
  model TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  extracted_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('EXTRACTED','EXTRACTED_WITH_DROPS','FAILED')),
  input_tokens INTEGER,
  output_tokens INTEGER,
  cost_usd TEXT,
  output_json TEXT NOT NULL,
  extraction_fingerprint TEXT NOT NULL UNIQUE,
  UNIQUE(document_sha256,model,prompt_version)
);
CREATE INDEX IF NOT EXISTS extraction_runs_ipo ON extraction_runs(ipo_id,source_type,extracted_at);

-- Deterministic post-IPO/pro-forma bridge.  This is deliberately separate from
-- valuation_runs so assumptions and earnings effects remain inspectable rather than
-- being laundered into a fair-value number.
CREATE TABLE IF NOT EXISTS proforma_runs (
  id INTEGER PRIMARY KEY,
  ipo_id INTEGER NOT NULL REFERENCES ipo(id),
  calculated_at TEXT NOT NULL,
  engine_version TEXT NOT NULL,
  inputs_json TEXT NOT NULL,
  outputs_json TEXT NOT NULL,
  missing_inputs_json TEXT,
  run_fingerprint TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS proforma_runs_ipo ON proforma_runs(ipo_id,calculated_at);

-- Explicit storage of the pipeline's normalized street read.  Individual articles stay
-- in ipo_news; this table is only the deterministic summary used by Command Center.
CREATE TABLE IF NOT EXISTS street_summary (
  ipo_id INTEGER PRIMARY KEY REFERENCES ipo(id),
  calculated_at TEXT NOT NULL,
  positive_count INTEGER NOT NULL DEFAULT 0,
  neutral_count INTEGER NOT NULL DEFAULT 0,
  negative_count INTEGER NOT NULL DEFAULT 0,
  summary_json TEXT NOT NULL,
  source_fingerprint TEXT NOT NULL UNIQUE
);
