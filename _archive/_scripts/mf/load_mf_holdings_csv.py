#!/usr/bin/env python3
"""
load_mf_holdings_csv.py — load a clean, pre-parsed MF holdings CSV into mf_scheme_holdings.

Input CSV columns (this file already has them):
  month, amc_name, scheme_name, stock_name, isin, sector, nse_symbol,
  quantity, market_value_cr, portfolio_weight_pct, market_value_lakh

Idempotent: upserts on (month, amc_name, scheme_name, isin) — re-runnable, and it does
NOT touch other AMCs already in the table (e.g. your earlier SBI/HDFC rows).

After loading, run build_isin_symbol_map.py to backfill nse_symbol (the CSV's symbol
column is empty; ISIN is 100% present, so the join fills it).

Run:  python _scripts/mf/load_mf_holdings_csv.py mf_holdings_final.csv
Env:  DATABASE_URL (or NEON_DATABASE_URL)
"""
import os, sys, csv, datetime
import psycopg2
from psycopg2.extras import execute_values

URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
if not URL:
    sys.exit("DATABASE_URL not set")
import argparse
_ap = argparse.ArgumentParser()
_ap.add_argument("csv_path")
_ap.add_argument("--type", choices=["monthly", "fortnight"], default="monthly",
                 help="disclosure type for these rows (monthly=authoritative)")
_args = _ap.parse_args()
CSV_PATH = _args.csv_path
DISCLOSURE_TYPE = _args.type.upper()

DDL = """
CREATE TABLE IF NOT EXISTS mf_scheme_holdings (
    id SERIAL PRIMARY KEY,
    month DATE NOT NULL,
    amc_name TEXT NOT NULL,
    scheme_name TEXT NOT NULL,
    stock_name TEXT,
    isin TEXT,
    sector TEXT,
    nse_symbol TEXT,
    quantity DOUBLE PRECISION,
    market_value_lakh DOUBLE PRECISION,
    market_value_cr DOUBLE PRECISION,
    portfolio_weight_pct DOUBLE PRECISION,
    disclosure_type TEXT DEFAULT 'MONTHLY',
    UNIQUE (month, amc_name, scheme_name, isin)
);
ALTER TABLE mf_scheme_holdings ADD COLUMN IF NOT EXISTS market_value_lakh DOUBLE PRECISION;
ALTER TABLE mf_scheme_holdings ADD COLUMN IF NOT EXISTS market_value_cr DOUBLE PRECISION;
ALTER TABLE mf_scheme_holdings ADD COLUMN IF NOT EXISTS disclosure_type TEXT DEFAULT 'MONTHLY';
"""

UPSERT = """
INSERT INTO mf_scheme_holdings
  (month, amc_name, scheme_name, stock_name, isin, sector, nse_symbol,
   quantity, market_value_lakh, market_value_cr, portfolio_weight_pct, disclosure_type)
VALUES %s
ON CONFLICT (month, amc_name, scheme_name, isin) DO UPDATE SET
  stock_name = EXCLUDED.stock_name,
  sector = EXCLUDED.sector,
  quantity = EXCLUDED.quantity,
  market_value_lakh = EXCLUDED.market_value_lakh,
  market_value_cr = EXCLUDED.market_value_cr,
  portfolio_weight_pct = EXCLUDED.portfolio_weight_pct,
  disclosure_type = EXCLUDED.disclosure_type
"""


def fnum(v):
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if s == "" or s.lower() in ("nan", "none", "null"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def fdate(v):
    s = str(v).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def main():
    rows = list(csv.DictReader(open(CSV_PATH, encoding="utf-8-sig")))
    print(f"read {len(rows):,} rows from {CSV_PATH}")

    values, skipped = [], 0
    for r in rows:
        month = fdate(r.get("month"))
        amc   = (r.get("amc_name") or "").strip()
        sch   = (r.get("scheme_name") or "").strip()
        isin  = (r.get("isin") or "").strip()
        # the conflict key needs all four; drop rows missing any (can't dedupe safely)
        if not (month and amc and sch and isin):
            skipped += 1
            continue
        values.append((
            month, amc, sch,
            (r.get("stock_name") or "").strip() or None,
            isin,
            (r.get("sector") or "").strip() or None,
            (r.get("nse_symbol") or "").strip() or None,   # empty in this file -> filled later by ISIN map
            fnum(r.get("quantity")),
            fnum(r.get("market_value_lakh")),
            fnum(r.get("market_value_cr")),
            fnum(r.get("portfolio_weight_pct")),
            DISCLOSURE_TYPE,
        ))

    conn = psycopg2.connect(URL); conn.autocommit = False
    cur = conn.cursor()
    cur.execute(DDL)
    execute_values(cur, UPSERT, values, page_size=1000)
    conn.commit()

    # report what's now in the table for these AMCs
    amcs = sorted({v[1] for v in values})
    cur.execute("""
        SELECT amc_name, COUNT(*), MIN(month), MAX(month),
               COUNT(DISTINCT isin), COUNT(nse_symbol)
        FROM mf_scheme_holdings
        WHERE amc_name = ANY(%s)
        GROUP BY amc_name ORDER BY amc_name
    """, (amcs,))
    print(f"\nupserted {len(values):,} rows  (skipped {skipped} missing-key rows)\n")
    print(f"  {'AMC':40s} {'rows':>7s} {'months':>18s} {'isins':>7s} {'sym✓':>6s}")
    for amc, c, mn, mx, ni, ns in cur.fetchall():
        print(f"  {amc:40s} {c:>7,d}  {str(mn)} .. {str(mx)} {ni:>6,d} {ns:>6,d}")
    cur.close(); conn.close()
    print("\nNext: python _scripts/build_isin_symbol_map.py   (backfills nse_symbol via ISIN)")


if __name__ == "__main__":
    main()
