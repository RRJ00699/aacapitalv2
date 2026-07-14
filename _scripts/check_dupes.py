#!/usr/bin/env python3
"""READ ONLY — find duplicate IPOs (same company, multiple rows) + their verdicts."""
import os,sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import psycopg2
DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn=psycopg2.connect(DB,connect_timeout=25);cur=conn.cursor()

# Kusumgar specifically
print("=== KUSUMGAR rows in ipo_consolidated ===")
cur.execute("""SELECT company_name, nse_symbol, symbol_final, listing_date, issue_size_cr, ipo_score
  FROM ipo_consolidated WHERE company_name ILIKE '%kusumgar%' ORDER BY company_name""")
for r in cur.fetchall(): print(f"  {r}")

print("\n=== KUSUMGAR verdicts ===")
cur.execute("""SELECT company_name, verdict, score, confidence FROM ipo_verdicts
  WHERE company_name ILIKE '%kusumgar%'""")
for r in cur.fetchall(): print(f"  {r}")

# general duplicate detection — same normalized name, multiple rows
print("\n=== ALL near-duplicate company names (consolidated) ===")
cur.execute("""
  WITH norm AS (
    SELECT company_name,
      LOWER(REGEXP_REPLACE(REGEXP_REPLACE(company_name,'\\s+(ltd|limited|pvt|private)\\.?',' ','gi'),'[^a-z0-9]','','g')) AS key
    FROM ipo_consolidated
  )
  SELECT key, COUNT(*) n, STRING_AGG(company_name, ' || ') names
  FROM norm GROUP BY key HAVING COUNT(*)>1 ORDER BY n DESC LIMIT 20
""")
dupes=cur.fetchall()
print(f"  found {len(dupes)} duplicate groups:")
for key,n,names in dupes: print(f"  [{n}x] {names[:90]}")
conn.close()
