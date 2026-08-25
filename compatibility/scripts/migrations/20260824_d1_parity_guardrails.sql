-- PROPOSAL ONLY: owner approval is required before applying this migration to D1.
CREATE UNIQUE INDEX IF NOT EXISTS ux_ipo_nse_symbol_nonnull
  ON ipo(nse_symbol) WHERE nse_symbol IS NOT NULL;

-- ipo_listing_band is intentionally NOT created here.  Repository history proves
-- only the reader contract (ipo_id, band_pct with values 5/10/20), not the complete
-- historical table key/provenance contract.  Import its exact Neon DDL with the owner
-- export rather than inventing an offer-price-band shape.

CREATE TRIGGER IF NOT EXISTS listing_outcomes_gap_insert_guard
BEFORE INSERT ON listing_outcomes WHEN ABS(NEW.gap_pct) > 300
BEGIN SELECT RAISE(ABORT, 'ABS(gap_pct) must be <= 300'); END;

CREATE TRIGGER IF NOT EXISTS listing_outcomes_gap_update_guard
BEFORE UPDATE OF gap_pct ON listing_outcomes WHEN ABS(NEW.gap_pct) > 300
BEGIN SELECT RAISE(ABORT, 'ABS(gap_pct) must be <= 300'); END;
