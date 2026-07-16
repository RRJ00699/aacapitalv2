# -*- coding: utf-8 -*-
"""dedup_merge.py — merge the 8 safe twin pairs in ipo_intelligence.
Same logic as dedup_merge.sql, but executed via psycopg2 so no SQL-console
quirks. Pair (861 RMC, 908 UEL) is SKIPPED (conflicting symbols — manual).
Keeper <- donor: fill-empty EVERY column, repoint name-keyed dependents,
delete donor. Prints a receipt per merge + final census + row count.
Run:  python _scripts/dedup_merge.py --apply     (without --apply = preview)
"""
import os, sys
import psycopg2

PAIRS = PAIRS = [
    (22,  1081),  # C.E. Info Systems      <- newer import
    (23,  1079),  # CMS Infosystems        <- newer import
    (904, 1141),  # Ravikumar Distilleries <- ALLCAPS import
    (66,  1085),  # SJS Enterprises        <- newer import
]
DEPS = [("ipo_verdicts","company_name"), ("ipo_flags","company_name"),
        ("ipo_rhp_intel","company_name"), ("ipo_broker_consensus","company")]

def main():
    apply = "--apply" in sys.argv
    conn = psycopg2.connect(os.environ["DATABASE_URL"]); conn.autocommit = False
    cur = conn.cursor()

    cur.execute("""SELECT column_name FROM information_schema.columns
                   WHERE table_name='ipo_intelligence'
                     AND column_name NOT IN ('id','company_name')""")
    cols = [r[0] for r in cur.fetchall()]
    print(f"{len(cols)} mergeable columns; mode = {'APPLY' if apply else 'PREVIEW'}")

    for keeper, donor in PAIRS:
        cur.execute("SELECT company_name, nse_symbol FROM ipo_intelligence WHERE id IN (%s,%s) ORDER BY id<>%s",
                    (keeper, donor, keeper))
        rows = cur.fetchall()
        if len(rows) != 2:
            print(f"  SKIP ({keeper},{donor}) — {len(rows)} row(s) found (already merged?)"); continue
        (kn, ks), (dn, ds) = rows
        print(f"  {keeper} '{kn}' [{ks or '-'}]  <-  {donor} '{dn}' [{ds or '-'}]")
        if not apply: continue

        for c in cols:
            cur.execute(
                f'UPDATE ipo_intelligence k SET "{c}" = COALESCE(k."{c}", d."{c}") '
                f'FROM ipo_intelligence d WHERE k.id=%s AND d.id=%s', (keeper, donor))
        for tbl, nc in DEPS:
            cur.execute("SELECT 1 FROM information_schema.tables WHERE table_name=%s", (tbl,))
            if not cur.fetchone(): continue
            cur.execute(f'DELETE FROM "{tbl}" WHERE "{nc}"=%s AND EXISTS (SELECT 1 FROM "{tbl}" x WHERE x."{nc}"=%s)',
                        (dn, kn))
            cur.execute(f'UPDATE "{tbl}" SET "{nc}"=%s WHERE "{nc}"=%s', (kn, dn))
        cur.execute("DELETE FROM ipo_intelligence WHERE id=%s", (donor,))
        print(f"    merged ✓")

    if apply:
        conn.commit()
        print("COMMITTED")
    else:
        conn.rollback()
        print("preview only — rerun with --apply")

    cur.execute("SELECT COUNT(*) FROM ipo_intelligence")
    print("ipo_intelligence rows:", cur.fetchone()[0], "(expect 763 after apply)")
    cur.execute(r"""WITH n AS (SELECT company_name,
        trim(regexp_replace(regexp_replace(regexp_replace(lower(company_name),
        '\y(limited|ltd\.?|pvt\.?|private|and)\y',' ','g'),'&',' ','g'),
        '[^a-z0-9]+',' ','g')) AS canon FROM ipo_intelligence)
        SELECT canon, COUNT(*) FROM n GROUP BY canon HAVING COUNT(*)>1""")
    left = cur.fetchall()
    print("remaining twin canons:", left if left else "NONE",
          "(m b switchgears expected — manual pair)")
    conn.close()

if __name__ == "__main__":
    main()
