#!/usr/bin/env python3
"""dedupe_deals.py — removes exact duplicates in institutional_large_deals
(same ticker,date,type,qty,price), keeping one per group. Snapshot first.
  python _scripts/dedupe_deals.py [--apply]"""
import os, sys, argparse

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    import psycopg2
    DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not DB: sys.exit("DATABASE_URL not set")
    conn = psycopg2.connect(DB, connect_timeout=20); cur = conn.cursor()
    cur.execute("""SELECT COUNT(*) - COUNT(DISTINCT (ticker,deal_date,transaction_type,quantity,trade_price))
                   FROM institutional_large_deals""")
    extra = cur.fetchone()[0]
    print(f"surplus duplicate rows: {extra}")
    if not a.apply:
        print("DRY RUN — --apply deletes surplus (keeps one per group)."); return
    cur.execute("""DELETE FROM institutional_large_deals d
                   WHERE d.ctid NOT IN (
                     SELECT MIN(ctid) FROM institutional_large_deals
                     GROUP BY ticker, deal_date, transaction_type, quantity, trade_price)""")
    print(f"deleted: {cur.rowcount}")
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM institutional_large_deals")
    print("rows now:", cur.fetchone()[0])
    conn.close()

if __name__ == "__main__":
    main()
