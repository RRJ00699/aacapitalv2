#!/usr/bin/env python3
"""
purge_old_delivery.py — keep delivery_data bounded to a rolling window (mirrors purge_old_candles.py).
Delivery rows are tiny (~1,450/day), but we bound + VACUUM so Neon storage stays flat. Default 10yr
matches the candle window. Override with PURGE_YEARS.
Env: DATABASE_URL ; PURGE_YEARS (default 10)
"""
import os, sys
import datetime as dt

URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
YEARS = int(os.environ.get("PURGE_YEARS", "10"))

def main():
    if not URL: sys.exit("DATABASE_URL not set")
    import psycopg2
    cutoff = dt.date.today() - dt.timedelta(days=YEARS * 365)
    conn = psycopg2.connect(URL); conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM delivery_data WHERE date < %s", (cutoff,))
    n = cur.fetchone()[0]
    cur.execute("DELETE FROM delivery_data WHERE date < %s", (cutoff,))
    print(f"deleted {n:,} delivery rows older than {cutoff} (keeping {YEARS}yr).")
    cur.execute("VACUUM (ANALYZE) delivery_data")
    print("VACUUM ANALYZE done.")
    conn.close()

if __name__ == "__main__":
    main()
