#!/usr/bin/env python3
"""fix_sectors.py — replace NULL/'Unknown' ipo_intelligence.sector with the
company's own Screener industry (symbol join). Only touches NULL/Unknown.
  python _scripts/fix_sectors.py [--apply]"""
import os, sys, argparse
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    import psycopg2
    DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not DB: sys.exit("DATABASE_URL not set")
    conn = psycopg2.connect(DB, connect_timeout=20); cur = conn.cursor()
    cur.execute("""SELECT i.id, sf.industry FROM ipo_intelligence i
                   JOIN stock_fundamentals sf
                     ON sf.nse_symbol = UPPER(COALESCE(NULLIF(i.nse_symbol,''), i.symbol))
                   WHERE (i.sector IS NULL OR i.sector = 'Unknown')
                     AND sf.industry IS NOT NULL""")
    rows = cur.fetchall()
    print(f"fixable sectors: {len(rows)}")
    if a.apply:
        for pid, ind in rows:
            cur.execute("""UPDATE ipo_intelligence SET sector=%s
                           WHERE id=%s AND (sector IS NULL OR sector='Unknown')""", (ind, pid))
        conn.commit(); print("applied")
    else:
        print("DRY RUN — --apply to write")
    conn.close()
if __name__ == "__main__":
    main()
