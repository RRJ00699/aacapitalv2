#!/usr/bin/env python3
"""READ ONLY — actual ipo_rhp_intel schema + is Laser's RHP data there?"""
import os,sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import psycopg2
DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn=psycopg2.connect(DB,connect_timeout=25);cur=conn.cursor()

# actual columns
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='ipo_rhp_intel' ORDER BY ordinal_position")
cols=[r[0] for r in cur.fetchall()]
print("=== ipo_rhp_intel columns ===")
print("  "+", ".join(cols))

# is Laser there?
cur.execute("SELECT COUNT(*) FROM ipo_rhp_intel WHERE company_name ILIKE '%laser%'")
print(f"\nLaser rows in ipo_rhp_intel: {cur.fetchone()[0]}")
cur.execute("SELECT company_name FROM ipo_rhp_intel WHERE company_name ILIKE '%laser%'")
for r in cur.fetchall(): print(f"  '{r[0]}'")

# show a sample row (first few cols) to see what's populated
key_cols=[c for c in cols if c in ('company_name','model','confidence','verdict','summary','one_line','full_json','raw_text')][:6]
if key_cols:
    cur.execute(f"SELECT {','.join(key_cols)} FROM ipo_rhp_intel WHERE company_name ILIKE '%laser%' LIMIT 1")
    r=cur.fetchone()
    if r:
        print("\n=== Laser RHP row (key fields) ===")
        for c,v in zip(key_cols,r):
            print(f"  {c}: {str(v)[:80]}")

# WHY does the score circle show 0.00 for laser/kusumgar? check what the API returns
# the circle uses (vscore ?? ipo_score) — both null. Where's 0.00 from?
print("\n=== why 0.00? check ipo_consolidated score fields for laser ===")
cur.execute("""SELECT company_name, ipo_score, score_band, listing_date, is_sme, issue_size_cr
  FROM ipo_consolidated WHERE company_name ILIKE '%laser%' OR company_name ILIKE '%kusumgar%' OR company_name ILIKE '%alpine%'""")
for r in cur.fetchall(): print(f"  {r}")
conn.close()
