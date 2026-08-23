-- 0005_source_facts.sql — append-only provenance ledger with true idempotency.
--
-- Status: CURRENT (Stage A, 5-table target D1 schema)
-- Idempotency (see D1_EVIDENCE_REPORT §6 note): observation_hash =
-- sha256(field || '|' || value || '|' || source || '|' || (document_sha ?? '')
--        || '|' || (pipeline_version ?? '')).
-- Two retries with identical values ⇒ same hash ⇒ 1 row (previous timestamp-
-- based PK let identical retries produce duplicates when fetched_at differed).

CREATE TABLE IF NOT EXISTS source_facts (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  ipo_id            INTEGER NOT NULL REFERENCES ipo(id) ON DELETE RESTRICT,

  field             TEXT    NOT NULL,        -- e.g. 'fundamentals.issue_price', 'ipo.status'
  value             TEXT,
  source            TEXT    NOT NULL,        -- 'nse' | 'sebi' | 'sbi' | 'kite' | 'ipomatrix' | 'derived' | 'manual'
  document_sha      TEXT,                    -- R2 blob sha256, when applicable
  confidence        TEXT,                    -- decimal string 0..1
  pipeline_version  TEXT,

  is_current        INTEGER NOT NULL DEFAULT 1,
  observation_hash  TEXT    NOT NULL,        -- sha256 hex, 64 chars
  fetched_at        TEXT    NOT NULL,

  UNIQUE (ipo_id, field, observation_hash),

  CHECK (
    confidence IS NULL
    OR (CAST(confidence AS REAL) >= 0.0 AND CAST(confidence AS REAL) <= 1.0)
  ),
  CHECK ( length(observation_hash) = 64 )
);

CREATE INDEX IF NOT EXISTS sf_ipo_field_idx    ON source_facts(ipo_id, field, fetched_at DESC);
CREATE INDEX IF NOT EXISTS sf_ipo_current_idx  ON source_facts(ipo_id, is_current);
CREATE INDEX IF NOT EXISTS sf_source_time_idx  ON source_facts(source, fetched_at DESC);
