#!/usr/bin/env python3
"""
reconcile_listing_dates.py — fixes the class of bug where a stock is LIVE on NSE
but the master still says 'lists <future date>' (Knack: card said Jul 8, traded
Jul 7). Truth = the first real trading candle. If price_candles has an earlier
first date than listing_date, listing_date was wrong -> correct it.

Only moves listing_date EARLIER to the first actual candle (a stock can't trade
before it lists). Never invents dates for IPOs with no candles yet (still upcoming).

  python _scripts/reconcile_listing_dates.py            # dry: shows mismatches
  python _scripts/reconcile_listing_dates.py --apply
"""
import os, sys, argparse

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    import psycopg2
    DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not DB: sys.exit("DATABASE_URL not set")
    conn = psycopg2.connect(DB, connect_timeout=20); cur = conn.cursor()
    # first real candle per IPO vs its stored listing_date
    cur.execute("""
        SELECT i.id, i.company_name, i.listing_date, MIN(p.date) AS first_candle
        FROM ipo_intelligence i
        JOIN price_candles p
          ON UPPER(p.symbol) = UPPER(COALESCE(NULLIF(i.nse_symbol,''), i.symbol))
        GROUP BY i.id, i.company_name, i.listing_date
        HAVING i.listing_date IS NULL OR MIN(p.date) < i.listing_date
    """)
    rows = cur.fetchall()
    print(f"IPOs whose first candle predates (or lacks) listing_date: {len(rows)}")
    fixed = 0
    for pid, nm, ld, first in rows:
        # guard: ignore absurd gaps (>400d) — likely a symbol collision, not a real fix
        if ld is not None and (ld - first).days > 400:
            print(f"  SKIP {nm[:30]}: gap {(ld-first).days}d too large (symbol collision?)")
            continue
        print(f"  {nm[:34]:36} {ld} -> {first}")
        fixed += 1
        if a.apply:
            cur.execute("UPDATE ipo_intelligence SET listing_date=%s WHERE id=%s", (first, pid))
    if a.apply:
        conn.commit()
        print(f"\nAPPLIED: {fixed} listing dates corrected to first-trade date.")
        print("Re-run build_ipo_consolidated + convergence so cards refresh status.")
    else:
        print(f"\nDRY RUN — would fix {fixed}. --apply to write.")
    conn.close()

if __name__ == "__main__":
    main()
