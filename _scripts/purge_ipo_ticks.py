#!/usr/bin/env python3
"""
purge_ipo_ticks.py — drop listing-day ticks once an IPO passes its anchor lock-in.

Ticks are captured only on listing day (ipo_tick_capture.py, 09:14–15:35) to feed the
LIVE floor/ceiling during the first sessions. Once the IPO reaches its anchor lock-in
(~listing + 30d), those ticks are dead weight — the floor/ceiling is already static and
stored in ipo_daily_levels. This deletes the whole tick set for any IPO whose lock-in
(anchor_lock30_date, or listing_date + 30d proxy) has passed, plus an optional buffer.

DRY-RUN by default; needs --apply to delete. IRREVERSIBLE.

  python _scripts\\purge_ipo_ticks.py                 # dry-run
  python _scripts\\purge_ipo_ticks.py --buffer 10     # keep 10 extra days past lock-in
  python _scripts\\purge_ipo_ticks.py --apply         # delete
Needs DATABASE_URL.
"""
import argparse, os, sys
try: import psycopg2
except ImportError: sys.exit("pip install psycopg2-binary --break-system-packages")

# an IPO is "matured" when its lock-in (+buffer) is already in the past
MATURED = """COALESCE(i.anchor_lock30_date, i.listing_date + interval '30 days')
             + (%s || ' days')::interval < now()"""

# safety net: ticks whose symbol has no IPO row / no listing_date, older than this many
# days, are also purged so orphaned rows can't linger forever (well past any 30d lock-in)
ORPHAN_DAYS = 60

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--buffer",type=int,default=0,help="extra calendar days to keep past lock-in")
    ap.add_argument("--apply",action="store_true")
    a=ap.parse_args()
    u=os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")
    if not u: sys.exit("Set DATABASE_URL.")
    conn=psycopg2.connect(u); cur=conn.cursor()

    cur.execute("SELECT count(*) FROM ipo_tick_feed"); total=cur.fetchone()[0]

    q_matured=f"""SELECT count(*) FROM ipo_tick_feed t
                  JOIN ipo_intelligence i ON i.nse_symbol = t.symbol
                  WHERE i.listing_date IS NOT NULL AND {MATURED}"""
    cur.execute(q_matured,(a.buffer,)); matured=cur.fetchone()[0]

    q_orphan=f"""SELECT count(*) FROM ipo_tick_feed t
                 WHERE NOT EXISTS (SELECT 1 FROM ipo_intelligence i
                                   WHERE i.nse_symbol = t.symbol AND i.listing_date IS NOT NULL)
                   AND t.ts < now() - interval '{ORPHAN_DAYS} days'"""
    cur.execute(q_orphan); orphan=cur.fetchone()[0]

    todel=matured+orphan
    print(f"ipo_tick_feed total: {total:,}")
    print(f"  matured past lock-in + {a.buffer}d: {matured:,}")
    print(f"  orphan ticks > {ORPHAN_DAYS}d (no IPO row): {orphan:,}")
    print(f"  → would delete: {todel:,}  (keep {total-todel:,})")
    if not a.apply:
        print("\nDRY-RUN. Re-run with --apply to delete. (Irreversible.)")
        return

    cur.execute(f"""DELETE FROM ipo_tick_feed t
                    USING ipo_intelligence i
                    WHERE i.nse_symbol = t.symbol AND i.listing_date IS NOT NULL AND {MATURED}""",(a.buffer,))
    d1=cur.rowcount
    cur.execute(f"""DELETE FROM ipo_tick_feed t
                    WHERE NOT EXISTS (SELECT 1 FROM ipo_intelligence i
                                      WHERE i.nse_symbol = t.symbol AND i.listing_date IS NOT NULL)
                      AND t.ts < now() - interval '{ORPHAN_DAYS} days'""")
    d2=cur.rowcount
    conn.commit()
    print(f"✓ deleted {d1:,} matured + {d2:,} orphan tick rows ({d1+d2:,} total).")

if __name__=="__main__": main()
