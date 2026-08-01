#!/usr/bin/env python3
"""
inspect_checks.py — READ-ONLY. The second half of the schema evidence.

inspect_schema.py gave columns and unique keys. It did NOT show CHECK constraints,
and three insights columns (category, direction, source_type) are NOT NULL text whose
legal values are defined by a CHECK, not by the column type. Writing a value the CHECK
rejects fails the insert; guessing them is not an option.

This dumps:
  1. every CHECK on the V2 tables the extractor writes
  2. the distinct values ALREADY stored in insights/rhp_findings (252/376 rows exist),
     which shows what the previous extraction actually used
  3. what the 4 existing documents rows look like (doc_type vocabulary)

Writes NOTHING. Sub-second. No API spend.

PC / PowerShell:
    python inspect_checks.py
"""
import os, sys, io
try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception: pass
import psycopg2

TABLES = ["insights", "rhp_findings", "valuation", "documents", "financial_statements"]


def main():
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL not set")
    conn = psycopg2.connect(url)
    cur = conn.cursor()

    print("=" * 72)
    print("1. CHECK CONSTRAINTS (the legal-value rules)")
    print("=" * 72)
    cur.execute("""
        SELECT rel.relname, con.conname, pg_get_constraintdef(con.oid)
          FROM pg_constraint con
          JOIN pg_class rel ON rel.oid = con.conrelid
          JOIN pg_namespace n ON n.oid = rel.relnamespace
         WHERE n.nspname = 'public'
           AND con.contype = 'c'
           AND rel.relname = ANY(%s)
         ORDER BY rel.relname, con.conname""", (TABLES,))
    rows = cur.fetchall()
    if not rows:
        print("  (none found)")
    for tbl, name, ddl in rows:
        print(f"\n  {tbl}.{name}")
        print(f"    {ddl}")

    print()
    print("=" * 72)
    print("2. VALUES ALREADY IN USE (what the prior extraction wrote)")
    print("=" * 72)

    for col in ["category", "direction", "source_type"]:
        cur.execute(f"""SELECT {col}, count(*) FROM insights
                        GROUP BY {col} ORDER BY count(*) DESC""")
        vals = cur.fetchall()
        print(f"\n  insights.{col}:")
        for v, n in vals:
            print(f"    {str(v):32} {n:>6}")

    cur.execute("""SELECT model, prompt_version, count(*) FROM rhp_findings
                   GROUP BY model, prompt_version ORDER BY count(*) DESC""")
    print("\n  rhp_findings (model, prompt_version):")
    for m, pv, n in cur.fetchall():
        print(f"    {str(m):32} {str(pv):20} {n:>6}")

    cur.execute("""SELECT count(*) FILTER (WHERE doc_id IS NULL), count(*) FROM rhp_findings""")
    dnull, dtot = cur.fetchone()
    print(f"\n  rhp_findings.doc_id NULL: {dnull}/{dtot}"
          f"   (the UNIQUE key is partial — it only applies WHERE doc_id IS NOT NULL)")

    cur.execute("""SELECT DISTINCT unnest(junk_signals) FROM rhp_findings
                   WHERE junk_signals IS NOT NULL LIMIT 30""")
    js = [r[0] for r in cur.fetchall()]
    print(f"  rhp_findings.junk_signals vocabulary in use: {js if js else '(none)'}")

    print()
    print("=" * 72)
    print("3. documents — doc_type vocabulary (only 4 rows exist)")
    print("=" * 72)
    cur.execute("""SELECT id, ipo_id, doc_type, page_count,
                          left(coalesce(url,'(null)'), 60), left(sha256, 12)
                     FROM documents ORDER BY id""")
    for r in cur.fetchall():
        print(f"   id={r[0]} ipo={r[1]} type={r[2]} pages={r[3]} url={r[4]} sha={r[5]}...")

    print()
    print("=" * 72)
    print("4. valuation.engine_version — what already exists")
    print("=" * 72)
    cur.execute("""SELECT engine_version, count(*), min(computed_at), max(computed_at)
                     FROM valuation GROUP BY engine_version ORDER BY count(*) DESC""")
    for ev, n, lo, hi in cur.fetchall():
        print(f"   {str(ev):20} {n:>6}   {lo}  ->  {hi}")

    conn.close()
    print("\ndone — nothing was written.")


if __name__ == "__main__":
    main()
