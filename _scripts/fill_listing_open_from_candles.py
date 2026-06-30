#!/usr/bin/env python3
"""
fill_listing_open_from_candles.py
=================================
Fills ipo_intelligence.listing_open from the REAL listing-day daily candle in
price_candles, for rows that have a listing_date + nse_symbol + a candle on that
date but a NULL listing_open.

Why this exists: backfill_ipo_ohlc.py is the full OHLC/returns backfill, but it is
gated to IPOs listed >7 days ago (so +90d return windows have history). A freshly
listed IPO (e.g. listed today) therefore can't get listing_open from it yet — which
leaves gap_bucket NULL in the consolidated table. This script fills ONLY listing_open
from the listing-day candle's open, so gap_bucket resolves immediately. The full
OHLC/returns still fill later via backfill_ipo_ohlc once past the 7-day mark.

Sync the candle first:
    python _scripts/kite-sync-candles.py --symbol TURTLEMINT --days 5 --target neon

Then:
    python _scripts/ipo/fill_listing_open_from_candles.py --symbol TURTLEMINT          # dry-run
    python _scripts/ipo/fill_listing_open_from_candles.py --symbol TURTLEMINT --apply  # write

Omit --symbol to do every eligible just-listed row at once.
"""
import os, sys, argparse, psycopg2, psycopg2.extras

DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", help="restrict to one nse_symbol (else all eligible)")
    ap.add_argument("--apply", action="store_true", help="write (default: dry-run)")
    args = ap.parse_args()
    if not DB:
        sys.exit("DATABASE_URL not set.")

    conn = psycopg2.connect(DB)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # rows with a listing-day candle but no listing_open yet
    q = """
        SELECT i.id, i.company_name, i.nse_symbol, i.issue_price,
               i.listing_date, c.open AS candle_open
        FROM ipo_intelligence i
        JOIN price_candles c
          ON c.symbol = i.nse_symbol
         AND c.date   = i.listing_date
        WHERE i.nse_symbol IS NOT NULL AND i.nse_symbol NOT IN ('', 'nan')
          AND i.listing_date IS NOT NULL
          AND i.listing_open IS NULL
          AND c.open IS NOT NULL
    """
    p = []
    if args.symbol:
        q += " AND i.nse_symbol ILIKE %s"
        p.append(f"%{args.symbol}%")
    q += " ORDER BY i.listing_date DESC"
    cur.execute(q, p)
    rows = cur.fetchall()

    if not rows:
        print("no rows to fill (need: listing_date + nse_symbol + a listing-day candle + null listing_open).")
        print("  → did you run kite-sync-candles for the symbol first?")
        conn.close()
        return

    print(f"{len(rows)} row(s) with a listing-day candle and null listing_open:\n")
    for r in rows:
        gap = None
        if r["issue_price"]:
            try:
                gap = round((float(r["candle_open"]) - float(r["issue_price"])) / float(r["issue_price"]) * 100, 1)
            except (TypeError, ZeroDivisionError):
                gap = None
        bucket = ("LOW" if gap is not None and gap < 10 else
                  "MID" if gap is not None and gap <= 30 else
                  "HIGH" if gap is not None else "?")
        print(f"  {r['nse_symbol']:14} listing {r['listing_date']}  issue {r['issue_price']}  "
              f"open {r['candle_open']}  → gap {gap}% ({bucket})")

    if not args.apply:
        print("\nDRY-RUN — add --apply to set listing_open.")
        conn.close()
        return

    ids = [r["id"] for r in rows]
    cur.execute("""
        UPDATE ipo_intelligence i
        SET listing_open = c.open
        FROM price_candles c
        WHERE c.symbol = i.nse_symbol
          AND c.date   = i.listing_date
          AND i.listing_open IS NULL
          AND i.id = ANY(%s)
    """, [ids])
    conn.commit()
    print(f"\nAPPLIED — set listing_open for {cur.rowcount} row(s).")
    print("Now rebuild: python _scripts/build_ipo_consolidated_v2.py  (gap_bucket will resolve)")
    conn.close()


if __name__ == "__main__":
    main()
