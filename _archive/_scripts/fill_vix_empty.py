#!/usr/bin/env python3
"""
fill_vix_empty.py — fill india_vix on EXISTING market_regimes rows that have it NULL,
using the same India VIX history from Kite. GOLDEN RULE: only touches rows where
india_vix IS NULL — never overwrites a populated value.

This pushes vix_source coverage from ~1,869 toward ~2,100 (the ~233 NIFTY-but-no-VIX
rows the backfill deliberately skipped because they already existed).

    python _scripts\\fill_vix_empty.py            # dry-run
    python _scripts\\fill_vix_empty.py --apply
"""
import os, sys, argparse
from datetime import date, timedelta
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
try:
    import psycopg2
    from kite_connect import get_kite
    from engines.market_regime import fetch_historical, INDIA_VIX_TOKEN
except Exception as e:
    sys.exit(f"Import failed ({e}). Run from _scripts/.")

def fetch_vix_chunked(kite, d0, d1, max_days=1800):
    """Kite caps historical_data at ~2000 days/call — fetch in windows."""
    out, cur = {}, d0
    while cur <= d1:
        end = min(cur + timedelta(days=max_days), d1)
        for c in fetch_historical(kite, INDIA_VIX_TOKEN, cur, end):
            out[c["date"].date()] = float(c["close"])
        cur = end + timedelta(days=1)
    return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true")
    ap.add_argument("--from", dest="frm", default="2015-01-01"); a = ap.parse_args()
    DB = os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")
    if not DB: sys.exit("Set DATABASE_URL.")
    conn = psycopg2.connect(DB); cur = conn.cursor()
    cur.execute("SELECT evaluation_date FROM market_regimes WHERE india_vix IS NULL ORDER BY evaluation_date")
    missing = [r[0] for r in cur.fetchall()]
    if not missing:
        print("no NULL-vix rows — nothing to do."); return
    print(f"rows with NULL india_vix: {len(missing)}  ({missing[0]} … {missing[-1]})")
    kite = get_kite()
    from datetime import datetime
    d0 = datetime.strptime(a.frm, "%Y-%m-%d").date()
    vmap = fetch_vix_chunked(kite, d0, date.today())
    fillable = [(d, vmap[d]) for d in missing if d in vmap]
    print(f"VIX history covers {len(fillable)} of those dates")
    if not a.apply:
        print("dry-run — nothing written. Re-run with --apply."); return
    n = 0
    for d, v in fillable:
        cur.execute("UPDATE market_regimes SET india_vix=%s WHERE evaluation_date=%s AND india_vix IS NULL", (v, d))
        n += cur.rowcount
    conn.commit()
    print(f"✓ filled india_vix on {n} existing rows (none overwritten).")

if __name__ == "__main__":
    main()
