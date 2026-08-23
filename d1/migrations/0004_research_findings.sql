-- 0004_research_findings.sql — AI / document-derived intelligence, always evidence-backed.
--
-- Status: CURRENT (Stage A, 5-table target D1 schema)
-- Replaces Neon: rhp_findings, insights, ipo_rhp_intel, ipo_research_notes.
-- A single evidence stream keyed by (ipo_id, finding_type, source_type, document_sha).

CREATE TABLE IF NOT EXISTS research_findings (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  ipo_id         INTEGER NOT NULL REFERENCES ipo(id) ON DELETE RESTRICT,

  finding_type   TEXT    NOT NULL,   -- 'rhp' | 'rhp_summary' | 'sbi_note' | 'broker_note'
                                     -- | 'anchor' | 'insight' | 'risk_factor' | 'peer_comment'
  source_type    TEXT    NOT NULL,   -- 'sebi_rhp' | 'sbi' | 'anchor_doc' | 'derived' | 'manual'
  document_sha   TEXT,               -- R2 blob sha256, when applicable

  finding        TEXT    NOT NULL,   -- JSON body (validated by ingest Worker)
  excerpt        TEXT,               -- short human-readable summary line
  page_number    INTEGER,

  severity       INTEGER,            -- 0..5 (higher = more severe)
  confidence     TEXT,               -- decimal string 0..1 (see CONVENTIONS §1)
  evidence_refs  TEXT,               -- JSON: [{page, quote, ...}]
  category       TEXT,               -- 'risk' | 'strength' | 'neutral' | ...
  direction      TEXT,               -- 'positive' | 'negative' | 'mixed' | 'neutral'

  model          TEXT,
  model_version  TEXT,
  prompt_version TEXT,
  cost_usd       TEXT,
  is_current     INTEGER NOT NULL DEFAULT 1,

  created_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),

  CHECK (
    confidence IS NULL
    OR (CAST(confidence AS REAL) >= 0.0 AND CAST(confidence AS REAL) <= 1.0)
  ),
  CHECK ( severity IS NULL OR (severity >= 0 AND severity <= 5) ),
  CHECK ( finding_type IN (
    'rhp','rhp_summary','sbi_note','broker_note','anchor','insight','risk_factor','peer_comment'
  ) )
);

-- Uniqueness on (doc + model + prompt) matches Neon's rhp_findings partial UNIQUE.
CREATE UNIQUE INDEX IF NOT EXISTS rf_doc_model_prompt_uidx
  ON research_findings(document_sha, model, prompt_version)
  WHERE document_sha IS NOT NULL AND model IS NOT NULL AND prompt_version IS NOT NULL;

CREATE INDEX IF NOT EXISTS rf_ipo_type_idx     ON research_findings(ipo_id, finding_type, created_at DESC);
CREATE INDEX IF NOT EXISTS rf_ipo_current_idx  ON research_findings(ipo_id, is_current);
