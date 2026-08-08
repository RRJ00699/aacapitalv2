#!/usr/bin/env python3
"""
purge_old_candles.py — keeps price_candles bounded to a rolling window (default 5y)
so Neon storage never grows unbounded. Deletes daily candles older than the window,
then VACUUMs so the space is reclaimed for reuse.

The miner only needs 3.5y and the similarity engine reads recent shape, so a 5y window
is comfortable. If storage gets tight, drop PURGE_YEARS to 4 (or 3.5) — that's the lever.

Run:  python _scripts/purge_old_candles.py
Env:  DATABASE_URL (or NEON_DATABASE_URL); PURGE_YEARS (optional, default 5)
"""
import os, sys, psycopg2

URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
if not URL:
    sys.exit("DATABASE_URL not set")

YEARS = os.environ.get("PURGE_YEARS", "5")

def main():
    conn = psycopg2.connect(URL); conn.autocommit = True
    cur = conn.cursor()
    interval = f"{YEARS} years"

    # daily candles
    cur.execute(f"DELETE FROM price_candles WHERE date < CURRENT_DATE - INTERVAL '{interval}'")
    deleted_daily = cur.rowcount
    print(f"price_candles: deleted {deleted_daily:,} rows older than {interval}")

    # weekly candles, if that table exists (harmless if it doesn't)
    try:
        cur.execute(f"DELETE FROM price_candles_weekly WHERE week_start < CURRENT_DATE - INTERVAL '{interval}'")
        print(f"price_candles_weekly: deleted {cur.rowcount:,} rows older than {interval}")
    except Exception:
        pass

    # reclaim space (VACUUM cannot run inside a transaction — autocommit is on)
    cur.execute("VACUUM (ANALYZE) price_candles")
    print("VACUUM ANALYZE price_candles done — space reclaimed for reuse")
    cur.close(); conn.close()

if __name__ == "__main__":
    main()
