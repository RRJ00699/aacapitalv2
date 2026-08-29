PRAGMA foreign_keys = ON;

-- Raw-first IPO Matrix staging. Every JSON file is stored exactly once by SHA.
-- Identity columns are convenience spine fields only; payload_json remains authoritative.
CREATE TABLE IF NOT EXISTS ipomatrix_raw_stage (
  sha256 TEXT PRIMARY KEY CHECK(length(sha256)=64),
  matrix_id INTEGER,
  company_name TEXT,
  name_norm TEXT,
  isin TEXT,
  filename TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  loaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ipomatrix_raw_stage_matrix_id ON ipomatrix_raw_stage(matrix_id);
CREATE INDEX IF NOT EXISTS ipomatrix_raw_stage_isin ON ipomatrix_raw_stage(isin);
CREATE INDEX IF NOT EXISTS ipomatrix_raw_stage_name_norm ON ipomatrix_raw_stage(name_norm);
