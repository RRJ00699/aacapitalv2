-- PROPOSAL ONLY: owner approval is required before applying this migration to D1.
CREATE UNIQUE INDEX IF NOT EXISTS ux_ipo_nse_symbol_nonnull
  ON ipo(nse_symbol) WHERE nse_symbol IS NOT NULL;

CREATE TABLE IF NOT EXISTS ipo_listing_band (
  ipo_id INTEGER PRIMARY KEY REFERENCES ipo(id),
  band_lo NUMERIC,
  band_hi NUMERIC,
  issue_price NUMERIC,
  source TEXT NOT NULL DEFAULT 'neon',
  CHECK (band_lo IS NULL OR band_lo >= 0),
  CHECK (band_hi IS NULL OR band_hi >= band_lo),
  CHECK (issue_price IS NULL OR (issue_price >= band_lo AND issue_price <= band_hi))
);

CREATE TRIGGER IF NOT EXISTS listing_outcomes_gap_insert_guard
BEFORE INSERT ON listing_outcomes WHEN ABS(NEW.gap_pct) > 300
BEGIN SELECT RAISE(ABORT, 'ABS(gap_pct) must be <= 300'); END;

CREATE TRIGGER IF NOT EXISTS listing_outcomes_gap_update_guard
BEFORE UPDATE OF gap_pct ON listing_outcomes WHEN ABS(NEW.gap_pct) > 300
BEGIN SELECT RAISE(ABORT, 'ABS(gap_pct) must be <= 300'); END;
