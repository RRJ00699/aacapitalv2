#!/usr/bin/env python3
"""
purge_ipo_ticks.py — drop listing-day ticks once an IPO passes its anchor lock-in.

Ticks are captured only on listing day (ipo_tick_capture.py) to feed the LIVE
floor/ceiling. Once the IPO reaches its anchor lock-in (~listing + 30d) those ticks
are dead weight — the floor/ceiling is already static in ipo_daily_levels. This
deletes the whole tick set for any IPO whose lock-in (anchor_lock30_date, or
listing_date + 30d proxy) has passed, plus an optional buffer.

Schema-robust: auto-discovers the tick timestamp column (name varies across setups)
for the orphan safety-net; the main lock-in purge only needs the `symbol` column.

DRY-RUN by default; needs --apply to delete. IRREVERSIBLE.

  python _scripts\\purge_ipo_ticks.py                 # dry-run
  python _scripts\\purge_ipo_ticks.py --buffer 10     # keep 10 extra days past lock-in
  python _scripts\\purge_ipo_ticks.py --apply         # delete
Needs DATABASE_URL.
"""
import argparse, os, sys
try: import psycopg2
except ImportError: sys.exit("pip install psycopg2-binary --break-system-packages")

MATURED = """COALESCE(i.anchor_lock30_date, i.listing_date + interval '30 days')
             + (%s || ' days')::interval < now()"""
ORPHAN_DAYS = 60

def ts_column(cur):
    """Find the timestamp column of ipo_tick_feed (name varies across setups)."""
    cur.execute("""SELECT column_name FROM information_schema.columns
                   WHERE table_name='ipo_tick_feed' AND data_type LIKE 'timestamp%'
                   ORDER BY ordinal_position LIMIT 1""")
    r=cur.fetchone(); return r[0] if r else None

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--buffer",type=int,default=0,help="extra calendar days to keep past lock-in")
    ap.add_argument("--apply",action="store_true")
    a=ap.parse_args()
    u=os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")
    if not u: sys.exit("Set DATABASE_URL.")
    conn=psycopg2.connect(u); cur=conn.cursor()

    cur.execute("SELECT count(*) FROM ipo_tick_feed"); total=cur.fetchone()[0]
    tscol=ts_column(cur)

    cur.execute(f"""SELECT count(*) FROM ipo_tick_feed t
                    JOIN ipo_intelligence i ON i.nse_symbol = t.symbol
                    WHERE i.listing_date IS NOT NULL AND {MATURED}""",(a.buffer,))
    matured=cur.fetchone()[0]

    orphan=0
    if tscol:
        cur.execute(f"""SELECT count(*) FROM ipo_tick_feed t
                        WHERE NOT EXISTS (SELECT 1 FROM ipo_intelligence i
                             WHERE i.nse_symbol=t.symbol AND i.listing_date IS NOT NULL)
                          AND t."{tscol}" < now() - interval '{ORPHAN_DAYS} days'""")
        orphan=cur.fetchone()[0]

    todel=matured+orphan
    print(f"ipo_tick_feed total: {total:,}  (ts column: {tscol or 'none found — orphan net skipped'})")
    print(f"  matured past lock-in + {a.buffer}d: {matured:,}")
    print(f"  orphan > {ORPHAN_DAYS}d (no IPO row): {orphan:,}")
    print(f"  → would delete: {todel:,}  (keep {total-todel:,})")
    if not a.apply:
        print("\nDRY-RUN. Re-run with --apply to delete. (Irreversible.)")
        return

    cur.execute(f"""DELETE FROM ipo_tick_feed t USING ipo_intelligence i
                    WHERE i.nse_symbol=t.symbol AND i.listing_date IS NOT NULL AND {MATURED}""",(a.buffer,))
    d1=cur.rowcount; d2=0
    if tscol:
        cur.execute(f"""DELETE FROM ipo_tick_feed t
                        WHERE NOT EXISTS (SELECT 1 FROM ipo_intelligence i
                             WHERE i.nse_symbol=t.symbol AND i.listing_date IS NOT NULL)
                          AND t."{tscol}" < now() - interval '{ORPHAN_DAYS} days'""")
        d2=cur.rowcount
    conn.commit()
    print(f"✓ deleted {d1:,} matured + {d2:,} orphan tick rows ({d1+d2:,} total).")

if __name__=="__main__": main()
