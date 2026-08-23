-- 0003_market_observations.sql — unified time-series (candles + pre-open + listing observations).
--
-- Status: CURRENT (Stage A, 5-table target D1 schema)
-- Replaces Neon: market_candles (1d), market_candles_15m (15m),
--                listing_observations (preopen/open/tick/close_d1),
--                ipo_tick_feed (tick, if archival retention is enabled).
--
-- One row per (ipo_id, interval, observation_type, observed_at). Retries
-- with the same tuple are no-ops via INSERT ... ON CONFLICT DO NOTHING.

CREATE TABLE IF NOT EXISTS market_observations (
  ipo_id            INTEGER NOT NULL REFERENCES ipo(id) ON DELETE RESTRICT,
  observed_at       TEXT    NOT NULL,           -- UTC ISO-8601 for intraday; YYYY-MM-DD for daily
  interval          TEXT    NOT NULL,           -- '1d' | '15m' | '5m' (future) | 'preopen' | 'tick'
  observation_type  TEXT    NOT NULL,           -- 'candle' | 'preopen' | 'open' | 'tick' | 'close_d1' | 'orderbook'

  -- Candle fields (nullable when not a candle)
  o                 TEXT,
  h                 TEXT,
  l                 TEXT,
  c                 TEXT,
  v                 INTEGER,

  -- Pre-open / listing observation fields
  ltp               TEXT,
  buy_qty           INTEGER,
  sell_qty          INTEGER,
  iep               TEXT,
  traded_qty        INTEGER,
  delivery_pct      TEXT,

  source            TEXT    NOT NULL,           -- 'kite' | 'nse' | 'bse'
  payload           TEXT,                       -- optional JSON (depth, extras)

  PRIMARY KEY (ipo_id, interval, observation_type, observed_at),

  -- Interval / observation_type whitelist so a stray writer can't invent junk.
  CHECK (interval IN ('1d','15m','5m','1m','preopen','tick')),
  CHECK (observation_type IN ('candle','preopen','open','tick','close_d1','orderbook','level')),
  -- Numeric guardrails via CAST-to-REAL (transient, per CONVENTIONS §1).
  CHECK ( o IS NULL OR CAST(o AS REAL) >= 0 ),
  CHECK ( h IS NULL OR CAST(h AS REAL) >= 0 ),
  CHECK ( l IS NULL OR CAST(l AS REAL) >= 0 ),
  CHECK ( c IS NULL OR CAST(c AS REAL) >= 0 ),
  CHECK ( v IS NULL OR v >= 0 )
);

CREATE INDEX IF NOT EXISTS mo_ipo_time_idx      ON market_observations(ipo_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS mo_interval_time_idx ON market_observations(interval, observed_at DESC);
