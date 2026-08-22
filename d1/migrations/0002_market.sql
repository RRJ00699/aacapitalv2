-- 0002_market.sql — market data, matched to Neon writer INSERTs
-- Sources: pipeline/fill_v2.py:163 (market_regimes), :173 (market_candles),
-- :193 (market_candles_15m), :218 (listing_observations), :149 (listing_outcomes).

PRAGMA foreign_keys = ON;

---------------------------------------------------------------------------
-- market_regimes — Neon shape (evaluation_date PK, active_regime, india_vix)
-- pipeline/fill_v2.py also writes extra columns dynamically; keep minimal.
---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS market_regimes (
  evaluation_date        TEXT PRIMARY KEY,                     -- IST YYYY-MM-DD
  active_regime          TEXT,
  india_vix              TEXT
);

---------------------------------------------------------------------------
-- market_candles — daily OHLCV + delivery% + traded_qty.
-- Neon writer: pipeline/fill_v2.py:173.
---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS market_candles (
  ipo_id                 INTEGER NOT NULL REFERENCES ipo(id) ON DELETE RESTRICT,
  d                      TEXT NOT NULL,                         -- IST YYYY-MM-DD
  o                      TEXT,
  h                      TEXT,
  l                      TEXT,
  c                      TEXT,
  v                      INTEGER,
  delivery_pct           TEXT,
  traded_qty             INTEGER,
  PRIMARY KEY (ipo_id, d)
);
CREATE INDEX IF NOT EXISTS market_candles_ipo_d_idx ON market_candles(ipo_id, d DESC);

---------------------------------------------------------------------------
-- market_candles_15m — 15-minute intraday. Neon writer: fill_v2.py:193.
---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS market_candles_15m (
  ipo_id                 INTEGER NOT NULL REFERENCES ipo(id) ON DELETE RESTRICT,
  ts                     TEXT NOT NULL,                         -- UTC ISO-8601
  o                      TEXT,
  h                      TEXT,
  l                      TEXT,
  c                      TEXT,
  v                      INTEGER,
  PRIMARY KEY (ipo_id, ts)
);
CREATE INDEX IF NOT EXISTS market_candles_15m_ipo_ts_idx ON market_candles_15m(ipo_id, ts DESC);

---------------------------------------------------------------------------
-- listing_observations — Neon writer: fill_v2.py:218
-- (ipo_id, observed_at, obs_type, ltp, qty, buy_qty, sell_qty, payload).
---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS listing_observations (
  ipo_id                 INTEGER NOT NULL REFERENCES ipo(id) ON DELETE RESTRICT,
  observed_at            TEXT NOT NULL,                         -- UTC ISO-8601
  obs_type               TEXT NOT NULL,                         -- e.g. 'preopen_iep', 'preopen_qty', 'preopen_orderbook', 'open', 'tick'
  ltp                    TEXT,
  qty                    INTEGER,
  buy_qty                INTEGER,
  sell_qty               INTEGER,
  payload                TEXT,                                  -- JSON blob (Neon: jsonb)
  PRIMARY KEY (ipo_id, obs_type, observed_at)
);
CREATE INDEX IF NOT EXISTS listing_obs_type_time_idx ON listing_observations(ipo_id, obs_type, observed_at DESC);

---------------------------------------------------------------------------
-- listing_outcomes — Neon writer: fill_v2.py:149 / conftest.py.
-- Note the 3 booleans are Neon BOOLEAN → INTEGER 0/1 here.
---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS listing_outcomes (
  ipo_id                 INTEGER PRIMARY KEY REFERENCES ipo(id) ON DELETE RESTRICT,
  listing_open           TEXT,
  d1_close               TEXT,
  gap_pct                TEXT,
  pool                   TEXT,
  best_close             TEXT,
  worst_close            TEXT,
  ceiling_20             INTEGER,                               -- BOOLEAN 0/1
  hold_positive_vs_open  INTEGER,                               -- BOOLEAN 0/1
  winner_35              INTEGER,                               -- BOOLEAN 0/1
  dataset_version        TEXT
);
