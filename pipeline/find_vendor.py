#!/usr/bin/env python3
"""
find_vendor.py — READ-ONLY. Locate where the IPOMatrix vendor payload actually lives.

The fallback must fill from the vendor data we already hold, but the repo references
IPOMatrix through several V1 paths and nothing proves which table holds the payload
today. This finds it instead of guessing a table name.

Reports:
  1. every public table whose name mentions matrix / vendor / raw / intel
  2. every table carrying an ipomatrix_id column
  3. every jsonb column in the DB (the payload is a JSON dump)
  4. for the 5 target IPOs: their ipomatrix_id, and whether financials exist anywhere

  python find_vendor.py
"""
import os, sys, io, json
try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception: pass
import psycopg2

TARGETS = [285, 659, 710, 709, 175, 85]


def main():
    conn = psycopg2.connect(os.environ["DATABASE_URL"]); cur = conn.cursor()

    print("=" * 70)
    print("1. TABLES whose name suggests vendor payload")
    print("=" * 70)
    cur.execute("""SELECT table_name FROM information_schema.tables
                    WHERE table_schema='public'
                      AND (table_name ILIKE '%matrix%' OR table_name ILIKE '%vendor%'
                           OR table_name ILIKE '%raw%'    OR table_name ILIKE '%intel%'
                           OR table_name ILIKE '%chittor%')
                    ORDER BY table_name""")
    for (t,) in cur.fetchall():
        cur.execute(f"SELECT count(*) FROM {t}")
        print(f"   {t:34} {cur.fetchone()[0]:>8} rows")

    print()
    print("=" * 70)
    print("2. TABLES carrying an ipomatrix_id column")
    print("=" * 70)
    cur.execute("""SELECT table_name FROM information_schema.columns
                    WHERE table_schema='public' AND column_name ILIKE '%ipomatrix%'
                    ORDER BY table_name""")
    for (t,) in cur.fetchall():
        print(f"   {t}")

    print()
    print("=" * 70)
    print("3. JSONB columns (the vendor dump is JSON)")
    print("=" * 70)
    cur.execute("""SELECT table_name, column_name FROM information_schema.columns
                    WHERE table_schema='public' AND data_type='jsonb'
                    ORDER BY table_name, column_name""")
    for t, c in cur.fetchall():
        cur.execute(f"SELECT count(*) FROM {t} WHERE {c} IS NOT NULL")
        print(f"   {t}.{c:24} {cur.fetchone()[0]:>8} non-null")

    print()
    print("=" * 70)
    print("4. THE 5 TARGETS + Indo-MIM: vendor id and financial coverage")
    print("=" * 70)
    cur.execute("""SELECT id, name_display, ipomatrix_id, isin FROM ipo
                    WHERE id = ANY(%s) ORDER BY id""", (TARGETS,))
    for i, n, mid, isin in cur.fetchall():
        cur.execute("""SELECT count(*), count(*) FILTER (WHERE total_income IS NOT NULL),
                              count(*) FILTER (WHERE total_debt IS NOT NULL),
                              string_agg(DISTINCT source, ',')
                         FROM financial_statements WHERE ipo_id=%s""", (i,))
        n_fin, n_ti, n_td, srcs = cur.fetchone()
        print(f"   id={i:<5} matrix_id={str(mid):<10} isin={str(isin):<14} "
              f"{str(n)[:26]:28} fin_rows={n_fin} total_income={n_ti} "
              f"total_debt={n_td} src={srcs}")

    conn.close()
    print("\ndone — nothing was written.")


if __name__ == "__main__":
    main()
