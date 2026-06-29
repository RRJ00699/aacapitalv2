#!/usr/bin/env python3
"""check_consolidated_row.py — eyeball one ipo_consolidated row end-to-end (read-only).

  python _scripts/check_consolidated_row.py                 # TURTLEMINT
  python _scripts/check_consolidated_row.py --symbol NYKAA
"""
import os, sys, argparse
import psycopg2

DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
if not DB:
    sys.exit("DATABASE_URL not set.")

ap = argparse.ArgumentParser()
ap.add_argument("--symbol", default="TURTLEMINT")
args = ap.parse_args()

FIELDS = ["company_name", "symbol_final", "nse_symbol", "symbol", "is_sme",
          "issue_price", "listing_open", "listing_date", "gap_bucket",
          "final_total", "roe", "pat_cr", "is_profitable", "valuation_premium",
          "regime_at_listing", "anchor_count", "anchor_quality",
          "floor_price", "ceiling_price", "floor_defenses", "level_verdict",
          "tp1_exit_note"]

conn = psycopg2.connect(DB); cur = conn.cursor()
cur.execute(f"SELECT {', '.join(FIELDS)} FROM ipo_consolidated WHERE symbol_final = %s",
            [args.symbol.upper()])
rows = cur.fetchall()
if not rows:
    print(f"No ipo_consolidated row with symbol_final = {args.symbol.upper()}")
    sys.exit(0)
for r in rows:
    print(f"\n=== {args.symbol.upper()} ===")
    for k, v in zip(FIELDS, r):
        print(f"  {k:20} {v}")
cur.close(); conn.close()
