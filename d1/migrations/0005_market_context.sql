PRAGMA foreign_keys = ON;

-- Global market context is stored once per timestamp, never duplicated per IPO.
CREATE TABLE market_context_bars (
  symbol TEXT NOT NULL CHECK(symbol IN ('NIFTY50','INDIAVIX')),
  interval TEXT NOT NULL CHECK(interval='5m'),
  ts TEXT NOT NULL,
  open_value TEXT NOT NULL,
  high_value TEXT NOT NULL,
  low_value TEXT NOT NULL,
  close_value TEXT NOT NULL,
  source_name TEXT NOT NULL,
  content_fingerprint TEXT NOT NULL UNIQUE,
  PRIMARY KEY(symbol,interval,ts)
);

CREATE INDEX market_context_bars_lookup
  ON market_context_bars(symbol,interval,ts);

-- One compact row per trading day. Historical Neon has breadth_pct and VIX;
-- advances/declines/PCR are nullable until an authoritative source is captured.
CREATE TABLE market_context_daily (
  d TEXT PRIMARY KEY,
  regime TEXT,
  vix_close TEXT,
  breadth_pct TEXT,
  advances INTEGER,
  declines INTEGER,
  pcr TEXT,
  source_name TEXT NOT NULL,
  content_fingerprint TEXT NOT NULL UNIQUE,
  CHECK (advances IS NULL OR advances >= 0),
  CHECK (declines IS NULL OR declines >= 0)
);

CREATE INDEX market_context_daily_lookup ON market_context_daily(d);
