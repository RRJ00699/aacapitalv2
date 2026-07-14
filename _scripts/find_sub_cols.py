#!/usr/bin/env python3
"""READ ONLY — what ARE the subscription columns? Why is score 0.00 for Laser?"""
import os,sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import psycopg2
DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn=psycopg2.connect(DB,connect_timeout=25);cur=conn.cursor()

# all columns mentioning sub / qib / anchor
cur.execute("""SELECT column_name FROM information_schema.columns
  WHERE table_name='ipo_consolidated' AND
  (column_name ILIKE '%sub%' OR column_name ILIKE '%qib%' OR column_name ILIKE '%anchor%'
   OR column_name ILIKE '%retail%' OR column_name ILIKE '%nii%' OR column_name ILIKE '%score%')
  ORDER BY column_name""")
print("=== subscription/anchor/score columns in ipo_consolidated ===")
for r in cur.fetchall(): print(f"  {r[0]}")

# what does Laser actually have in those?
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='ipo_consolidated' AND (column_name ILIKE '%sub%' OR column_name ILIKE '%qib%' OR column_name ILIKE '%anchor%')")
subcols=[r[0] for r in cur.fetchall()]
if subcols:
    q=f"SELECT company_name,{','.join(subcols)} FROM ipo_consolidated WHERE company_name ILIKE '%laser%'"
    cur.execute(q)
    print("\n=== Laser's actual subscription values ===")
    r=cur.fetchone()
    if r:
        print(f"  company: {r[0]}")
        for c,v in zip(subcols,r[1:]): print(f"  {c}: {v}")
conn.close()
