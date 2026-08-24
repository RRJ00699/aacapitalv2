PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS rate_limit_log (
  id INTEGER PRIMARY KEY,
  rate_key TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS rate_limit_log_key_time ON rate_limit_log(rate_key, created_at);

CREATE TABLE IF NOT EXISTS pipeline_steps (
  id INTEGER PRIMARY KEY,
  step TEXT NOT NULL,
  ok INTEGER NOT NULL CHECK(ok IN (0,1)),
  error TEXT,
  ran_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS pipeline_steps_time ON pipeline_steps(ran_at);

CREATE TABLE IF NOT EXISTS pipeline_failures (
  id INTEGER PRIMARY KEY,
  step TEXT NOT NULL,
  script TEXT,
  stderr_tail TEXT,
  failed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS pipeline_failures_time ON pipeline_failures(failed_at);

CREATE TABLE IF NOT EXISTS job_runs (
  id INTEGER PRIMARY KEY,
  job TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('queued','running','done','failed','cancelled')),
  requested_by TEXT,
  requested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  started_at TEXT,
  finished_at TEXT,
  exit_code INTEGER,
  error TEXT,
  log_tail TEXT
);
CREATE INDEX IF NOT EXISTS job_runs_status ON job_runs(status, requested_at);
