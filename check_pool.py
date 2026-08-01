#!/usr/bin/env python3
"""
check_pool.py — READ-ONLY. Two answers in one run, no PowerShell quoting to fight.

  1. The listing_outcomes CHECK constraints + the pool labels ALREADY stored.
     kite_fetch.derive_outcome writes Negative/Flat/Warm/Heavy and every write was
     rejected by outcome_pool_valid on the 08-01 run, so the real vocabulary has to
     come from the DB rather than from me guessing a second time.

  2. WHY each IPO in the active window qualified — its issue dates and document
     freshness. The first version of that query used ipo.created_at and wrongly
     surfaced Suryoday Bank / Engineers India as "upcoming", so the selection needs
     to show its evidence rather than be trusted.

  python check_pool.py
"""
import os, sys, io
try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception: pass
import psycopg2

IDS = [12, 10, 11, 648, 236]


def main():
    conn = psycopg2.connect(os.environ["DATABASE_URL"]); cur = conn.cursor()

    print("=" * 68)
    print("1. listing_outcomes CHECK constraints")
    print("=" * 68)
    cur.execute("""SELECT con.conname, pg_get_constraintdef(con.oid)
                     FROM pg_constraint con
                     JOIN pg_class rel ON rel.oid = con.conrelid
                    WHERE rel.relname = 'listing_outcomes' AND con.contype = 'c'
                    ORDER BY con.conname""")
    rows = cur.fetchall()
    if not rows:
        print("   (none)")
    for name, ddl in rows:
        print(f"   {name}")
        print(f"      {ddl}")

    print()
    print("=" * 68)
    print("2. pool labels ALREADY stored (the vocabulary to match)")
    print("=" * 68)
    cur.execute("""SELECT pool, count(*) FROM listing_outcomes
                    GROUP BY pool ORDER BY count(*) DESC""")
    for p, n in cur.fetchall():
        print(f"   {str(p):20} {n:>6}")

    print()
    print("=" * 68)
    print("3. WHY each selected IPO qualified as active")
    print("=" * 68)
    for i in IDS:
        cur.execute("""SELECT i.id, i.name_display, i.status, i.listing_date, i.created_at,
                              ii.open_date, ii.close_date, ii.band_lo, ii.band_hi,
                              (SELECT max(d.fetched_at) FROM documents d WHERE d.ipo_id=i.id)
                         FROM ipo i LEFT JOIN ipo_issue ii ON ii.ipo_id = i.id
                        WHERE i.id = %s""", (i,))
        r = cur.fetchone()
        if not r:
            print(f"   id={i} not found"); continue
        print(f"\n   id={r[0]:<5} {str(r[1])[:40]}")
        print(f"      status={r[2]}  listing_date={r[3]}  row_created={str(r[4])[:10]}")
        print(f"      issue open={r[5]}  close={r[6]}  band={r[7]}-{r[8]}")
        print(f"      newest document fetched: {r[9]}")
        reasons = []
        if r[5]: reasons.append(f"open_date {r[5]}")
        if r[6]: reasons.append(f"close_date {r[6]}")
        if r[9]: reasons.append(f"document {str(r[9])[:10]}")
        print(f"      -> qualified on: {', '.join(reasons) if reasons else 'NOTHING VISIBLE — investigate'}")

    conn.close()
    print("\ndone — nothing was written.")


if __name__ == "__main__":
    main()
