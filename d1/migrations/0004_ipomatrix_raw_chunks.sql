PRAGMA foreign_keys = ON;

-- Large IPO Matrix payloads are stored in deterministic SQL-safe chunks.
-- The parent row keeps the identity/spine metadata; SHA256 remains the file identity.
ALTER TABLE ipomatrix_raw_stage ADD COLUMN chunk_count INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS ipomatrix_raw_stage_chunks (
  sha256 TEXT NOT NULL REFERENCES ipomatrix_raw_stage(sha256) ON DELETE CASCADE,
  chunk_no INTEGER NOT NULL CHECK(chunk_no >= 0),
  payload_chunk TEXT NOT NULL,
  PRIMARY KEY(sha256, chunk_no)
);

CREATE INDEX IF NOT EXISTS ipomatrix_raw_stage_chunks_sha
  ON ipomatrix_raw_stage_chunks(sha256, chunk_no);
