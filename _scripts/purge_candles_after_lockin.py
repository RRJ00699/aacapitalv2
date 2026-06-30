#!/usr/bin/env python3
"""
purge_candles_after_lockin.py — trim price_candles to the pre-lock-in window (our game).
Deletes candles dated AFTER each IPO's lock-in (anchor_lock30_date, or listing_date+30d proxy),
plus an optional buffer. DRY-RUN by default; needs --apply to actually delete.

⚠️ IRREVERSIBLE. This removes the post-lock tail (e.g. the T+40-hold backtest data).
   It does NOT touch the pre-lock window (listing → ~T+30), which covers exit-on-strength
   (≤10 sessions) and days-to-peak (≤18). Keep a DB snapshot first if unsure.

  python _scripts\\purge_candles_after_lockin.py                 # dry-run, buffer 0
  python _scripts\\purge_candles_after_lockin.py --buffer 10     # keep 10 extra sessions
  python _scripts\\purge_candles_after_lockin.py --apply         # delete
Needs DATABASE_URL.
"""
import argparse, os, sys
try: import psycopg2
except ImportError: sys.exit("pip install psycopg2-binary --break-system-packages")

CUTOFF = """COALESCE(i.anchor_lock30_date, i.listing_date + interval '30 days')
            + (%s || ' days')::interval"""

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--buffer",type=int,default=0,help="extra calendar days to keep past lock-in")
    ap.add_argument("--apply",action="store_true")
    a=ap.parse_args()
    u=os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")
    if not u: sys.exit("Set DATABASE_URL.")
    conn=psycopg2.connect(u); cur=conn.cursor()
    cur.execute("SELECT count(*) FROM price_candles"); total=cur.fetchone()[0]
    q_count=f"""SELECT count(*) FROM price_candles pc
                JOIN ipo_intelligence i ON i.nse_symbol = pc.symbol
                WHERE i.listing_date IS NOT NULL AND pc.date > {CUTOFF}"""
    cur.execute(q_count,(a.buffer,)); todel=cur.fetchone()[0]
    print(f"price_candles total: {total:,}")
    print(f"after lock-in + {a.buffer}d buffer → would delete: {todel:,}  (keep {total-todel:,})")
    if not a.apply:
        print("\nDRY-RUN. Re-run with --apply to delete. (Keep a snapshot first — irreversible.)")
        return
    cur.execute(f"""DELETE FROM price_candles pc
                    USING ipo_intelligence i
                    WHERE i.nse_symbol = pc.symbol AND i.listing_date IS NOT NULL
                      AND pc.date > {CUTOFF}""",(a.buffer,))
    conn.commit()
    print(f"✓ deleted {cur.rowcount:,} post-lock-in candle rows.")

if __name__=="__main__": main()
