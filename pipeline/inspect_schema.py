#!/usr/bin/env python3
"""
inspect_schema.py — READ-ONLY. Two jobs:
  1. Prove WHICH database/host DATABASE_URL points at, and whether the V2 table
     family is present alongside the V1 debris.
  2. Dump the real columns of the V2 tables the RHP v2-full extractor must write to,
     so nothing downstream is written against a guessed column name.

Writes NOTHING. No API spend. Sub-second.

PC / PowerShell:
    python inspect_schema.py
"""
import os, sys, io
try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception: pass
import psycopg2

# tables the v2-full extraction path will touch (these GATE the "safe to build" verdict)
V2_TARGETS = ["rhp_findings", "insights", "valuation", "documents",
              "financial_statements", "source_facts", "ipo_issue"]
# the rest of the V2 canonical family — written by the pipeline (fill_v2 / kite_fetch),
# NOT the RHP extractor, so they do not gate the verdict below. Enumerated so every V2
# table is DECLARED: an undeclared table looks like debris, which is exactly how the
# dropped intraday_30d got swept. market_candles_15m (PK ipo_id,ts) is its V2 successor.
V2_DATA_FILL = ["ipo", "subscription_snapshots", "market_candles", "market_candles_15m",
                "listing_outcomes", "listing_observations", "market_regimes", "decisions"]
# V1 debris — presence is expected and harmless; we just must never WRITE here.
# NOTE: intraday_30d is NOT listed here — it was dropped and SUPERSEDED by the V2 table
# market_candles_15m; classifying it as debris is what got its data swept. Do not re-add.
V1_DEBRIS  = ["ipo_intelligence", "ipo_consolidated", "ipo_golden", "ipo_master",
              "ipo_rhp_intel"]


def main():
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL not set")
    conn = psycopg2.connect(url)
    cur = conn.cursor()

    print("=" * 72)
    print("1. CONNECTION IDENTITY")
    print("=" * 72)
    cur.execute("SELECT current_database(), current_user, version()")
    db, user, ver = cur.fetchone()
    print(f"  database : {db}")
    print(f"  user     : {user}")
    print(f"  server   : {ver.split(',')[0]}")
    # host comes from the URL, not the server (Neon is behind a pooler)
    host = url.split("@")[-1].split("/")[0] if "@" in url else "(unparsed)"
    print(f"  host     : {host}")

    cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
    total = cur.fetchone()[0]
    print(f"  public tables: {total}   (74 was the recorded V1+V2 tangled count)")

    print()
    print("=" * 72)
    print("2. TABLE FAMILIES")
    print("=" * 72)
    cur.execute("""SELECT table_name FROM information_schema.tables
                   WHERE table_schema='public'""")
    present = {r[0] for r in cur.fetchall()}

    print("  V2 targets (fill_v2 / extractor WRITE here):")
    for t in V2_TARGETS:
        mark = "OK " if t in present else "MISSING"
        print(f"    [{mark}] {t}")
    print("  V2 data-fill family (pipeline writes; NOT extractor-gated):")
    for t in V2_DATA_FILL:
        mark = "OK " if t in present else "absent "
        print(f"    [{mark}] {t}")
    print("  V1 debris (must never be written to):")
    for t in V1_DEBRIS:
        mark = "present" if t in present else "absent "
        print(f"    [{mark}] {t}")

    missing = [t for t in V2_TARGETS if t not in present]
    print()
    print("  VERDICT: " + ("V2 family COMPLETE — safe to build against"
                           if not missing else
                           f"V2 INCOMPLETE — missing {missing} — STOP, do not build"))

    print()
    print("=" * 72)
    print("3. COLUMNS — the V2 tables the extractor writes")
    print("=" * 72)
    for t in ["rhp_findings", "insights", "valuation", "documents"]:
        if t not in present:
            print(f"\n-- {t}: NOT PRESENT --")
            continue
        cur.execute("""SELECT column_name, data_type, is_nullable, column_default
                       FROM information_schema.columns
                       WHERE table_schema='public' AND table_name=%s
                       ORDER BY ordinal_position""", (t,))
        rows = cur.fetchall()
        print(f"\n-- {t} ({len(rows)} cols) --")
        for name, dtype, nullable, default in rows:
            d = f" default={default}" if default else ""
            print(f"   {name:28} {dtype:26} {'NULL' if nullable=='YES' else 'NOT NULL'}{d}")

    print()
    print("=" * 72)
    print("4. UNIQUE / PK CONSTRAINTS (the real dedup keys)")
    print("=" * 72)
    cur.execute("""SELECT t.relname, i.relname, idx.indisunique, idx.indisprimary,
                          pg_get_indexdef(idx.indexrelid)
                   FROM pg_index idx
                   JOIN pg_class i ON i.oid = idx.indexrelid
                   JOIN pg_class t ON t.oid = idx.indrelid
                   WHERE t.relname = ANY(%s) AND (idx.indisunique OR idx.indisprimary)
                   ORDER BY t.relname, i.relname""",
                (["rhp_findings", "insights", "valuation", "documents"],))
    for tbl, iname, uniq, pk, ddl in cur.fetchall():
        kind = "PK" if pk else "UNIQUE"
        print(f"  {tbl:18} {kind:7} {iname}")
        print(f"      {ddl}")

    print()
    print("=" * 72)
    print("5. CURRENT ROW COUNTS (context, not a write)")
    print("=" * 72)
    for t in ["rhp_findings", "insights", "valuation", "documents", "financial_statements"]:
        if t not in present:
            continue
        cur.execute(f"SELECT count(*) FROM {t}")
        print(f"   {t:24} {cur.fetchone()[0]:>8}")
    # how full is total_income already?
    if "financial_statements" in present:
        cur.execute("""SELECT count(*) FILTER (WHERE total_income IS NOT NULL),
                              count(*) FILTER (WHERE revenue IS NOT NULL), count(*)
                       FROM financial_statements""")
        ti, rv, tot = cur.fetchone()
        print(f"\n   financial_statements: total_income filled {ti}/{tot}, revenue filled {rv}/{tot}")

    conn.close()
    print("\ndone — nothing was written.")


if __name__ == "__main__":
    main()
