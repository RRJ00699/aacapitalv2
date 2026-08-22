-- 0003_engine.sql — engine outputs matched to Neon writers.
-- Sources: pipeline/fill_v2.py, pipeline/rhp_writer.py, pipeline/verdict_engine.py,
-- pipeline/score_engine.py (writers themselves), and pipeline/conftest.py.
--
-- NOTE ON VERDICT COLUMNS: Neon's `decisions` table stores TWO verdicts
-- (fundamental_verdict, listing_action). This matches
-- docs/specifications/AACAPITAL_PRODUCT_CONTRACT.md §4 — Company Quality and
-- Trade Setup are separate scoring systems (`quality_score`, `gap_bucket`,
-- `score_band`) each in their own table. The 3-way UI split (Company
-- Quality / Trade Setup / Live Action) is a *presentation* concern
-- assembled by the snapshot builder from these two verdicts + valuation +
-- pre-open data. D1 does NOT invent a third column.

PRAGMA foreign_keys = ON;

---------------------------------------------------------------------------
-- valuation — pipeline/conftest.py:50 verified against score_engine writer
---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS valuation (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  ipo_id                 INTEGER NOT NULL REFERENCES ipo(id) ON DELETE RESTRICT,
  computed_at            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  engine_version         TEXT,
  pe                     TEXT,
  pb                     TEXT,
  roe                    TEXT,
  roce                   TEXT,
  de                     TEXT,
  rev_cagr_3y            TEXT,
  ofs_pct                TEXT,
  peer_median_pe         TEXT,
  score                  TEXT,
  score_band             TEXT,                                  -- product contract §4 band chip
  inputs_used            TEXT,                                  -- JSON (Neon: jsonb)
  missing_inputs         TEXT                                   -- JSON array (Neon: text[])
);
CREATE INDEX IF NOT EXISTS valuation_ipo_time_idx ON valuation(ipo_id, computed_at DESC);

---------------------------------------------------------------------------
-- decisions — pipeline/conftest.py:55 verified against verdict_engine writer
---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS decisions (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  ipo_id                 INTEGER NOT NULL REFERENCES ipo(id) ON DELETE RESTRICT,
  decided_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  engine_version         TEXT,
  fundamental_verdict    TEXT,                                  -- GOOD | NEUTRAL | WEAK
  listing_action         TEXT,                                  -- BUY NOW | WAIT | AVOID
  reasons                TEXT,                                  -- JSON (Neon: jsonb)
  evidence_refs          TEXT,                                  -- JSON (Neon: jsonb)

  -- Product contract §6 hard rule: WEAK fundamentals must NEVER produce
  -- a BUY-family listing_action. Enforced at storage layer.
  CHECK ( NOT (fundamental_verdict = 'WEAK' AND listing_action LIKE 'BUY%') )
);
CREATE INDEX IF NOT EXISTS decisions_ipo_time_idx ON decisions(ipo_id, decided_at DESC);

---------------------------------------------------------------------------
-- rhp_findings — pipeline/fill_v2.py:234 comment (schema verified 2026-07-31)
-- Neon has a PARTIAL UNIQUE index on (doc_id, model, prompt_version)
-- WHERE doc_id IS NOT NULL. SQLite/D1 supports partial indexes ✔.
---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rhp_findings (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  ipo_id                 INTEGER NOT NULL REFERENCES ipo(id) ON DELETE RESTRICT,
  doc_id                 TEXT,                                  -- documents.sha256 (may be NULL for legacy)
  model                  TEXT,
  prompt_version         TEXT,
  findings               TEXT NOT NULL,                         -- JSON (Neon: jsonb NOT NULL)
  red_flag_count         INTEGER,
  junk_signals           TEXT,                                  -- JSON array (Neon: text[])
  confidence             TEXT,                                  -- 0..1 decimal string
  cost_usd               TEXT,
  analyzed_at            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),

  -- Neon CHECK: rhp_conf_range — confidence NULL or 0..1.
  CHECK ( confidence IS NULL
          OR (CAST(confidence AS REAL) >= 0.0 AND CAST(confidence AS REAL) <= 1.0) )
);
CREATE UNIQUE INDEX IF NOT EXISTS rhp_findings_dedup_uidx
  ON rhp_findings(doc_id, model, prompt_version) WHERE doc_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS rhp_findings_ipo_idx ON rhp_findings(ipo_id, analyzed_at DESC);

---------------------------------------------------------------------------
-- insights — _scripts/tests/test_intelligence_sql_integration.py:15
---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS insights (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  ipo_id                 INTEGER NOT NULL REFERENCES ipo(id) ON DELETE RESTRICT,
  excerpt                TEXT,
  page_number            INTEGER,
  doc_id                 TEXT,                                  -- documents.sha256
  category               TEXT,
  direction              TEXT,
  source_type            TEXT,
  is_current             INTEGER                                -- BOOLEAN 0/1
);
CREATE INDEX IF NOT EXISTS insights_ipo_current_idx ON insights(ipo_id, is_current);
