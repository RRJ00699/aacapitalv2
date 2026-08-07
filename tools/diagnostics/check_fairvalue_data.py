#!/usr/bin/env python3
"""READ ONLY — do we have the inputs for the fair-value model? (EPS, peer PE, ROE, CAGR, D/E, OFS%)"""
import os,sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import psycopg2
DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn=psycopg2.connect(DB,connect_timeout=25);cur=conn.cursor()

# what valuation-ish columns exist in ipo_consolidated?
cur.execute("""SELECT column_name FROM information_schema.columns
  WHERE table_name='ipo_consolidated' AND
  (column_name ILIKE '%eps%' OR column_name ILIKE '%pe%' OR column_name ILIKE '%roe%'
   OR column_name ILIKE '%cagr%' OR column_name ILIKE '%debt%' OR column_name ILIKE '%peer%'
   OR column_name ILIKE '%ofs%' OR column_name ILIKE '%fresh%' OR column_name ILIKE '%proceeds%'
   OR column_name ILIKE '%fair%' OR column_name ILIKE '%valuation%' OR column_name ILIKE '%revenue%')
  ORDER BY column_name""")
cols=[r[0] for r in cur.fetchall()]
print("=== valuation-input columns present ===")
for c in cols: print(f"  {c}")

# coverage: how many IPOs actually HAVE these populated?
print("\n=== coverage (non-null count / 767) ===")
for c in cols:
    try:
        cur.execute(f"SELECT COUNT(*) FROM ipo_consolidated WHERE {c} IS NOT NULL")
        print(f"  {c:28} {cur.fetchone()[0]}")
    except: pass

# does ipo_rhp_intel have use-of-proceeds / OFS info?
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='ipo_rhp_intel' AND (column_name ILIKE '%ofs%' OR column_name ILIKE '%proceed%' OR column_name ILIKE '%fresh%' OR column_name ILIKE '%use%')")
print("\n=== RHP proceeds/OFS columns ===")
for r in cur.fetchall(): print(f"  {r[0]}")
conn.close()
