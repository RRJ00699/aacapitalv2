#!/usr/bin/env python3
"""
dedup_valuation.py — remove DUPLICATE valuation rows (a script YOU run).

The old write_valuation used computed_at=now(), so every scoring run appended an
identical row (Indo-MIM had 4 identical v2-score-2 rows). score_engine is now
idempotent, but the existing duplicates remain. This removes them.

A "duplicate" = two rows with the SAME (ipo_id, engine_version) AND identical COMPUTED
values (pe,pb,roe,roce,de,rev_cagr_3y,ofs_pct,peer_median_pe,score,score_band,
missing_inputs). The NEWEST computed_at of each identical group is KEPT; older identical
copies are deleted. Genuinely different rows (a real rescore that changed a value) are
never touched. inputs_used is provenance and is not part of the identity, matching the
engine's idempotency check.

  python dedup_valuation.py               # DRY RUN — shows what would be deleted
  python dedup_valuation.py --apply       # actually delete (take a Neon branch first)
"""
import os, sys, io, argparse
if __name__ == "__main__":
    try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception: pass
import psycopg2

RANKED = """
  WITH ranked AS (
    SELECT ctid, ipo_id, engine_version, computed_at,
           row_number() OVER (
             PARTITION BY ipo_id, engine_version, pe, pb, roe, roce, de, rev_cagr_3y,
                          ofs_pct, peer_median_pe, score, score_band, missing_inputs
             ORDER BY computed_at DESC
           ) AS rn
    FROM valuation)
"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="perform the delete (default is dry-run)")
    a = ap.parse_args()

    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("Refusing to run: set DATABASE_URL (the DB to clean) first.")
    host = url.split("@")[-1].split("/")[0]
    print(f"  target DB host : {host}")
    print(f"  mode           : {'APPLY (will delete)' if a.apply else 'DRY RUN (no writes)'}\n")

    conn = psycopg2.connect(url, connect_timeout=30); cur = conn.cursor()

    cur.execute(RANKED + " SELECT count(*) FROM ranked")
    total = cur.fetchone()[0]
    cur.execute(RANKED + " SELECT count(*) FROM ranked WHERE rn>1")
    dupes = cur.fetchone()[0]
    cur.execute(RANKED + """
        SELECT ipo_id, engine_version, count(*) FROM ranked WHERE rn>1
        GROUP BY 1,2 ORDER BY 3 DESC LIMIT 20""")
    top = cur.fetchall()

    print(f"  valuation rows total       : {total}")
    print(f"  duplicate rows to delete   : {dupes}")
    print(f"  rows kept                  : {total - dupes}")
    if top:
        print("\n  top affected (ipo_id, engine_version, dup rows removed):")
        for ipo_id, ev, n in top:
            print(f"     id={ipo_id:<5} {str(ev):14} -{n}")

    if not a.apply:
        print("\n  DRY RUN — nothing deleted. Re-run with --apply to delete (Neon branch first).")
        conn.close(); return

    cur.execute(RANKED + " DELETE FROM valuation WHERE ctid IN (SELECT ctid FROM ranked WHERE rn>1)")
    deleted = cur.rowcount
    conn.commit()
    print(f"\n  DELETED {deleted} duplicate rows. Kept the newest of each identical group.")
    conn.close()


if __name__ == "__main__":
    main()
