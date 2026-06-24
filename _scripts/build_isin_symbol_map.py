#!/usr/bin/env python3
"""
build_isin_symbol_map.py — maps ISIN -> NSE symbol and backfills mf_scheme_holdings.nse_symbol.

MF portfolio files give ISIN, not ticker. This makes your holdings queryable by NSE symbol
(so "does stock X have MF backing?" and joins against price_candles / shareholding work).

Source: NSE's official equity list CSV (has SYMBOL + ISIN NUMBER columns), the exact, free,
canonical mapping. Download it once and drop it at data/EQUITY_L.csv:
    https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv
(or from NSE site: Market Data → Securities Available for Trading → Equity list)

Run:  python _scripts/build_isin_symbol_map.py
Env:  DATABASE_URL (or NEON_DATABASE_URL)
      EQUITY_LIST_CSV  path to EQUITY_L.csv (default data/EQUITY_L.csv)
"""
import os, sys, csv
import psycopg2
from psycopg2.extras import execute_values

URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
if not URL:
    sys.exit("DATABASE_URL not set")

CSV_PATH = os.environ.get("EQUITY_LIST_CSV", "data/EQUITY_L.csv")


def norm(h):
    return (h or "").strip().lower().replace("_", " ")


def read_equity_list(path):
    if not os.path.exists(path):
        sys.exit(f"Equity list not found at {path}\n"
                 "Download it from https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv "
                 "and place it there (or set EQUITY_LIST_CSV).")
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = [norm(h) for h in next(reader)]
        # find the symbol and isin columns regardless of exact spacing
        try:
            i_sym = next(i for i, h in enumerate(header) if h == "symbol")
            i_isin = next(i for i, h in enumerate(header) if "isin" in h)
        except StopIteration:
            sys.exit(f"Could not find SYMBOL / ISIN columns. Header was: {header}")
        for r in reader:
            if len(r) <= max(i_sym, i_isin):
                continue
            sym = r[i_sym].strip().upper()
            isin = r[i_isin].strip().upper()
            if sym and isin.startswith("INE"):
                rows.append((isin, sym))
    return rows


def main():
    rows = read_equity_list(CSV_PATH)
    if not rows:
        sys.exit("No ISIN/symbol rows parsed from the equity list.")
    print(f"Parsed {len(rows):,} ISIN->symbol pairs from {CSV_PATH}")

    conn = psycopg2.connect(URL); conn.autocommit = True
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS isin_symbol_map (
            isin TEXT PRIMARY KEY,
            nse_symbol TEXT NOT NULL
        )
    """)
    execute_values(cur, """
        INSERT INTO isin_symbol_map (isin, nse_symbol) VALUES %s
        ON CONFLICT (isin) DO UPDATE SET nse_symbol = EXCLUDED.nse_symbol
    """, rows, page_size=1000)
    cur.execute("SELECT COUNT(*) FROM isin_symbol_map")
    print(f"isin_symbol_map now holds {cur.fetchone()[0]:,} mappings")

    # backfill mf_scheme_holdings.nse_symbol via exact ISIN match
    cur.execute("""
        UPDATE mf_scheme_holdings m
        SET nse_symbol = map.nse_symbol
        FROM isin_symbol_map map
        WHERE m.isin = map.isin
          AND (m.nse_symbol IS NULL OR m.nse_symbol <> map.nse_symbol)
    """)
    updated = cur.rowcount

    # report coverage
    cur.execute("SELECT COUNT(*) FROM mf_scheme_holdings")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM mf_scheme_holdings WHERE nse_symbol IS NOT NULL")
    mapped = cur.fetchone()[0]
    cur.execute("""
        SELECT DISTINCT stock_name, isin
        FROM mf_scheme_holdings
        WHERE nse_symbol IS NULL
        ORDER BY stock_name
        LIMIT 15
    """)
    unmatched = cur.fetchall()

    print(f"\nBackfilled nse_symbol on {updated:,} holding rows")
    print(f"Coverage: {mapped:,}/{total:,} rows mapped ({mapped/total*100:.1f}%)")
    if unmatched:
        print("\nSample still-unmatched (likely delisted, merged, or non-NSE names):")
        for name, isin in unmatched:
            print(f"  {isin}  {name}")
        print("These are usually fine to leave null — old positions in names no longer on NSE.")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
