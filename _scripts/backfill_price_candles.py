#!/usr/bin/env python3
"""
backfill_price_candles.py — one-time bulk load of full daily history from
data/candles/daily/*.csv into price_candles.

Why: the live daily sync only appends recent candles, so price_candles is shallow
(~58 weeks deepest). The multibagger miner needs >=182 weeks (3.5yr) per symbol.
These CSVs hold the full history (e.g. 360ONE = 2019->2026), so loading them gives
the miner the depth it needs. The live sync keeps things current afterwards.

Idempotent: ON CONFLICT (symbol, date) DO UPDATE, so re-running is safe and resumable.
Each file's symbol = the filename (360ONE.csv -> 360ONE).

Run:  python _scripts/backfill_price_candles.py
Env:  DATABASE_URL (or NEON_DATABASE_URL)
      CANDLE_DIR (optional, default data/candles/daily)
"""
import os, sys, csv, glob, logging
import psycopg2
from psycopg2.extras import execute_values

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger()

URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
if not URL:
    sys.exit("DATABASE_URL not set")

CANDLE_DIR = os.environ.get("CANDLE_DIR", "data/candles/daily")
BATCH = 5000
# Only load the trailing N years — matches the rolling window the purge keeps, so the
# backfill and the steady state agree and Neon never holds more than ~5y of daily.
YEARS = int(os.environ.get("BACKFILL_YEARS", "5"))
import datetime as _dt
CUTOFF = (_dt.date.today() - _dt.timedelta(days=YEARS * 366)).isoformat()


def parse_rows(path, symbol):
    """Read one CSV (Date,Open,High,Low,Close,Volume) into insert tuples."""
    out = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        next(reader, None)  # skip header
        for row in reader:
            if len(row) < 6 or not row[0].strip():
                continue
            if row[0].strip() < CUTOFF:      # skip anything older than the rolling window
                continue
            try:
                out.append((
                    symbol, row[0].strip(),
                    float(row[1]), float(row[2]), float(row[3]), float(row[4]),
                    int(float(row[5] or 0)),
                ))
            except (ValueError, TypeError):
                continue
    return out


def main():
    files = sorted(glob.glob(os.path.join(CANDLE_DIR, "*.csv")))
    if not files:
        sys.exit(f"No CSVs found in {CANDLE_DIR} — run this from the repo root, "
                 f"or set CANDLE_DIR to where the daily candle CSVs live.")
    log.info(f"Found {len(files)} candle files in {CANDLE_DIR}; keeping candles on/after {CUTOFF} ({YEARS}y)")

    conn = psycopg2.connect(URL); conn.autocommit = False
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS price_candles (
            id BIGSERIAL PRIMARY KEY, symbol TEXT NOT NULL, date DATE NOT NULL,
            open NUMERIC(12,4), high NUMERIC(12,4), low NUMERIC(12,4),
            close NUMERIC(12,4), volume BIGINT, UNIQUE (symbol, date))
    """)
    conn.commit()

    total_rows, loaded_symbols = 0, 0
    for idx, path in enumerate(files, 1):
        symbol = os.path.splitext(os.path.basename(path))[0].upper()
        rows = parse_rows(path, symbol)
        if not rows:
            continue
        for i in range(0, len(rows), BATCH):
            execute_values(cur, """
                INSERT INTO price_candles (symbol, date, open, high, low, close, volume)
                VALUES %s
                ON CONFLICT (symbol, date) DO UPDATE SET
                    open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
                    close=EXCLUDED.close, volume=EXCLUDED.volume
            """, rows[i:i+BATCH])
        conn.commit()
        total_rows += len(rows); loaded_symbols += 1
        if idx % 50 == 0:
            log.info(f"[{idx}/{len(files)}] {symbol}: {len(rows)} rows  (cumulative {total_rows:,})")

    log.info(f"Backfill complete: {loaded_symbols} symbols, {total_rows:,} rows into price_candles")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
