#!/usr/bin/env python3
"""
export_ipo_backtest.py — pull the data needed to backtest the post-listing floor /
recovery-through-anchor-lock-in study, into CSVs you can upload.

Writes to ./ipo_backtest_export/ :
  1. ipo_meta.csv      — ipo_consolidated, ALL columns (one row per IPO).
                          Carries every quality field + the lock-in dates. We filter in the backtest.
  2. ipo_candles.csv    — daily OHLCV from price_candles for mainboard >=Rs200cr listed IPOs,
                          windowed listing_date .. listing_date + 130d (covers both lock-ins + absorption).
  3. market_index.csv   — (best effort) a broad index daily close, for exogenous-vs-mechanical dip tagging.
                          If no index series is found, this is skipped — not required for the core study.

Read-only. No writes to the DB. Run:  python _scripts/ipo/export_ipo_backtest.py
"""
import os, sys, csv

try:
    import psycopg2
except ImportError:
    sys.exit("pip install psycopg2-binary")

DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
OUTDIR = os.path.join(os.getcwd(), "ipo_backtest_export")


def db():
    if not DB:
        sys.exit("DATABASE_URL not set.")
    return psycopg2.connect(DB)


def dump(cur, sql, params, path, label):
    try:
        cur.execute(sql, params or [])
    except Exception as e:
        # roll back the aborted tx so later queries still run
        cur.connection.rollback()
        print(f"  [skip] {label}: {e}")
        return 0
    cols = [d[0] for d in cur.description]
    n = 0
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for row in cur:
            w.writerow(["" if v is None else v for v in row])
            n += 1
    print(f"  [ok]   {label}: {n} rows -> {path}")
    return n


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    conn = db(); cur = conn.cursor()

    # 1) metadata — every column, every IPO (filter happens in the backtest)
    dump(cur,
         "SELECT * FROM ipo_consolidated",
         None,
         os.path.join(OUTDIR, "ipo_meta.csv"),
         "ipo_meta (ipo_consolidated.*)")

    # 2) candles — mainboard >=Rs200cr listed IPOs, listing .. +130d
    dump(cur, """
        SELECT c.symbol, c.date, c.open, c.high, c.low, c.close, c.volume
        FROM price_candles c
        JOIN ipo_consolidated m ON m.symbol_final = c.symbol
        WHERE m.issue_size_cr >= 200 AND m.issue_size_cr < 100000
          AND m.listing_date IS NOT NULL
          AND c.date >= m.listing_date
          AND c.date <= (m.listing_date + INTERVAL '130 days')::date
        ORDER BY c.symbol, c.date
    """, None, os.path.join(OUTDIR, "ipo_candles.csv"),
         "ipo_candles (listing..+130d)")

    # 3) market index — best effort (used later for exogenous-dip tagging; optional)
    got = dump(cur, """
        SELECT symbol, date, close
        FROM price_candles
        WHERE upper(symbol) IN ('NIFTY50','NIFTY','NIFTY_50','NIFTY50INDEX','NIFTYBEES','^NSEI','NSEI')
        ORDER BY symbol, date
    """, None, os.path.join(OUTDIR, "market_index.csv"),
         "market_index (broad index)")
    if got == 0:
        # fallback: try the regimes table if it exists
        dump(cur, "SELECT * FROM market_regimes ORDER BY 1",
             None, os.path.join(OUTDIR, "market_index.csv"),
             "market_index (market_regimes fallback)")

    cur.close(); conn.close()
    print(f"\nDone. Upload the CSVs from:\n  {OUTDIR}")


if __name__ == "__main__":
    main()
