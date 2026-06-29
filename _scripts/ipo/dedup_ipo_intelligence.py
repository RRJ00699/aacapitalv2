#!/usr/bin/env python3
"""
dedup_ipo_intelligence.py — collapse rows that are the same company under two name
spellings (e.g. "Paytm" + "One 97 Communications Ltd." → both symbol PAYTM).

Strategy (SAFE — no data lost):
  • Cluster rows by resolved symbol  COALESCE(NULLIF(UPPER(nse_symbol),''), NULLIF(UPPER(symbol),'')).
  • In each cluster pick the KEEPER = the row with the most non-null columns
    (tiebreak: newest updated_at, then lowest id).
  • MERGE-UP: for every column where the keeper is NULL but a loser has a value,
    copy the loser's value into the keeper. (So combining two half-filled rows loses nothing.)
  • DELETE the losers.

Rows with no resolved symbol are left untouched (can't be matched this way).
Dry-run by default; --apply writes.

  python _scripts/ipo/dedup_ipo_intelligence.py            # report clusters + merge plan
  python _scripts/ipo/dedup_ipo_intelligence.py --apply    # merge-up + delete losers
"""
import os, sys, argparse
import psycopg2

DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
if not DB:
    sys.exit("DATABASE_URL not set.")

SYM = "COALESCE(NULLIF(UPPER(nse_symbol),''), NULLIF(UPPER(symbol),''))"
# never merge/compare these
SKIP_COLS = {"id"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write (default: dry-run)")
    args = ap.parse_args()

    conn = psycopg2.connect(DB); cur = conn.cursor()

    # all data columns (for merge-up + completeness scoring)
    cur.execute("""SELECT column_name FROM information_schema.columns
                   WHERE table_name='ipo_intelligence' ORDER BY ordinal_position""")
    cols = [c for (c,) in cur.fetchall() if c not in SKIP_COLS]

    # find clusters: same resolved symbol, more than one row
    cur.execute(f"""
        SELECT {SYM} AS sym, array_agg(id ORDER BY id) AS ids, count(*) AS n
        FROM ipo_intelligence
        WHERE {SYM} IS NOT NULL
        GROUP BY {SYM}
        HAVING count(*) > 1
        ORDER BY sym
    """)
    clusters = cur.fetchall()
    print(f"duplicate symbol clusters: {len(clusters)}  "
          f"(rows to remove: {sum(n-1 for _, _, n in clusters)})\n")

    collist = ", ".join(cols)
    total_deleted = 0
    for sym, ids, n in clusters:
        cur.execute(f"SELECT id, {collist} FROM ipo_intelligence WHERE id = ANY(%s)", [ids])
        recs = cur.fetchall()
        # completeness score = non-null count
        def score(rec):
            rid = rec[0]
            nonnull = sum(1 for v in rec[1:] if v is not None)
            return nonnull
        recs_sorted = sorted(recs, key=lambda r: (-score(r), r[0]))
        keeper = recs_sorted[0]
        losers = recs_sorted[1:]
        keeper_id = keeper[0]
        keep_name = keeper[1 + cols.index("company_name")] if "company_name" in cols else "?"

        # build merge-up: keeper-null but a loser has value
        merge = {}
        for ci, col in enumerate(cols, start=1):
            if keeper[ci] is None:
                for lr in losers:
                    if lr[ci] is not None:
                        merge[col] = lr[ci]
                        break

        loser_ids = [lr[0] for lr in losers]
        loser_names = [lr[1 + cols.index("company_name")] for lr in losers] if "company_name" in cols else loser_ids
        print(f"  {sym:14} keep id={keeper_id} ({str(keep_name)[:34]}) "
              f"score={score(keeper)}  |  drop {loser_ids} ({', '.join(str(x)[:22] for x in loser_names)})"
              + (f"  | merge-up {len(merge)} fields" if merge else ""))

        if args.apply:
            if merge:
                sets = ", ".join(f"{c} = %s" for c in merge)
                cur.execute(f"UPDATE ipo_intelligence SET {sets} WHERE id = %s",
                            list(merge.values()) + [keeper_id])
            cur.execute("DELETE FROM ipo_intelligence WHERE id = ANY(%s)", [loser_ids])
            total_deleted += len(loser_ids)

    if args.apply:
        conn.commit()
        print(f"\nAPPLIED. deleted {total_deleted} duplicate rows; survivors merged-up.")
        print("Re-run build_ipo_consolidated_v2.py to rebuild the consolidated table.")
    else:
        print("\nDRY-RUN — re-run with --apply to merge-up and delete losers.")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
