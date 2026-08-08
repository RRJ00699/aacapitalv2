-- ============================================================================
-- LEDGER #14 TRIAGE — run against PROD Neon (read-only), paste output back.
-- PC (PowerShell):  psql $env:DATABASE_URL -f _scripts/triage_known_gaps.sql
-- Splits the 40 contract gaps into KIND 1 (test DDL incomplete — seed the
-- contract DB) vs KIND 2 (route references a dead column — fix the route).
-- SELECT-only. Nothing here writes.
-- ============================================================================

-- 1) Do the suspected KIND-1 tables exist, and how big?
SELECT 'TABLE' AS kind, t.tbl,
       to_regclass('public.' || t.tbl) IS NOT NULL AS exists_in_prod,
       COALESCE((SELECT reltuples::bigint FROM pg_class WHERE relname = t.tbl), 0) AS approx_rows
FROM (VALUES
  ('platform_config'), ('kite_session'), ('market_snapshot'),
  ('rhp_run_log'), ('daily_institutional_flows'), ('user_sessions'),
  ('secrets_vault'), ('zerodha_tokens'), ('watchlists'), ('thesis'),
  ('nifty_snapshots'), ('access_notes'), ('job_runs'), ('ipo_journal')
) AS t(tbl)
ORDER BY exists_in_prod DESC, t.tbl;

-- 2) Do the suspected KIND-2 columns exist on their tables?
SELECT 'COLUMN' AS kind, c.tbl || '.' || c.col AS ref,
       EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = c.tbl AND column_name = c.col) AS exists_in_prod
FROM (VALUES
  -- flagged possible dead refs (KIND 2 candidates)
  ('ipo_intelligence', 'archetype'),
  ('ipo_consolidated', 'lqi_final'),
  ('ipo_consolidated', 'play_recommendation'),
  ('ipo_consolidated', 'listing_day_close'),
  ('ipo_consolidated', 'day_open'),
  -- known-good control (proves the method): reviewer-cited KIND 1
  ('ipo_intelligence', 'anchor_count'),
  -- remaining column gaps from the audit
  ('ipo_consolidated', 'gmp_trend'),
  ('ipo_intelligence', 'listing_gain_pct'),
  ('ipo_level_analysis', 'day_high'),
  ('ipo_tick_feed', 'oi'),
  ('price_candles', 'vwap')
) AS c(tbl, col)
ORDER BY exists_in_prod, ref;

-- 3) Full column lists for the two core tables (covers anything I missed):
SELECT 'ipo_consolidated' AS tbl, string_agg(column_name, ', ' ORDER BY ordinal_position)
FROM information_schema.columns WHERE table_name = 'ipo_consolidated'
UNION ALL
SELECT 'ipo_intelligence', string_agg(column_name, ', ' ORDER BY ordinal_position)
FROM information_schema.columns WHERE table_name = 'ipo_intelligence';
