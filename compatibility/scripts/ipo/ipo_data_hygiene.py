#!/usr/bin/env python3
"""
ipo_data_hygiene.py — two safe, idempotent fixes for ipo_intelligence:

  1) NEUTRALISE 'nan' symbols  — rows where a pandas NaN got stringified to the literal
     'nan'. These would make --auto-today try to subscribe Kite to a symbol named "nan".
     We set symbol = NULL (keeps the row + its data; just stops it polluting capture).

  2) BACKFILL listing_open from ipo_tick_feed — the NSE scrape can't know the *realized*
     opening price; only live ticks do. For any symbol with a captured listing-day series
     and a null listing_open, write the earliest tick LTP on listing_date back to
     ipo_intelligence.listing_open. Self-healing: every future captured IPO gets its open.

Dry-run by default. Add --apply to write.

  python _scripts/ipo/ipo_data_hygiene.py            # show what WOULD change
  python _scripts/ipo/ipo_data_hygiene.py --apply    # actually write
"""
import os, sys, argparse

try:
    import psycopg2
except ImportError:
    sys.exit("pip install psycopg2-binary")

DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
if not DB:
    sys.exit("DATABASE_URL not set.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    args = ap.parse_args()

    conn = psycopg2.connect(DB)
    cur = conn.cursor()

    # ---- 1) 'nan' symbols ----
    cur.execute("SELECT COUNT(*) FROM ipo_intelligence WHERE symbol = 'nan'")
    nan_count = cur.fetchone()[0]
    print(f"[1] rows with symbol = 'nan' : {nan_count}")
    if nan_count:
        cur.execute("SELECT company_name FROM ipo_intelligence WHERE symbol = 'nan' LIMIT 10")
        for (name,) in cur.fetchall():
            print(f"      - {name}")
        if args.apply:
            cur.execute("UPDATE ipo_intelligence SET symbol = NULL WHERE symbol = 'nan'")
            print(f"    -> set symbol = NULL on {cur.rowcount} rows")

    # ---- 2) backfill listing_open from earliest listing-day tick ----
    # candidates: symbol present, listing_open null, listing_date present, and we have ticks
    cur.execute("""
        SELECT i.symbol, i.listing_date
        FROM ipo_intelligence i
        WHERE i.symbol IS NOT NULL AND i.symbol <> 'nan'
          AND i.listing_open IS NULL
          AND i.listing_date IS NOT NULL
          AND EXISTS (SELECT 1 FROM ipo_tick_feed t WHERE t.symbol = i.symbol)
    """)
    cands = cur.fetchall()
    print(f"\n[2] symbols missing listing_open WITH captured ticks : {len(cands)}")

    fixed = 0
    for sym, ld in cands:
        # earliest tick LTP on the listing date (IST)
        cur.execute("""
            SELECT ltp FROM ipo_tick_feed
            WHERE symbol = %s AND (recorded_at AT TIME ZONE 'Asia/Kolkata')::date = %s
              AND ltp IS NOT NULL
            ORDER BY recorded_at ASC
            LIMIT 1
        """, [sym, ld])
        row = cur.fetchone()
        if not row:
            # no ticks exactly on listing_date — fall back to the very first tick we have
            cur.execute("""
                SELECT ltp FROM ipo_tick_feed
                WHERE symbol = %s AND ltp IS NOT NULL
                ORDER BY recorded_at ASC LIMIT 1
            """, [sym])
            row = cur.fetchone()
        if not row:
            continue
        open_px = float(row[0])
        print(f"      {sym}: listing_open <- {open_px:.2f}")
        if args.apply:
            cur.execute("UPDATE ipo_intelligence SET listing_open = %s WHERE symbol = %s AND listing_open IS NULL",
                        [open_px, sym])
            fixed += cur.rowcount

    if args.apply:
        conn.commit()
        print(f"\nAPPLIED. listing_open backfilled on {fixed} rows; 'nan' symbols neutralised.")
    else:
        print("\nDRY-RUN (no writes). Re-run with --apply to commit these changes.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
