#!/usr/bin/env python3
"""READ ONLY — does the fuzzy join ACTUALLY match Laser? Test the exact SQL the API runs."""
import os,sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import psycopg2
DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn=psycopg2.connect(DB,connect_timeout=25);cur=conn.cursor()

# 1. exact names in both tables
print("=== names ===")
cur.execute("SELECT company_name FROM ipo_consolidated WHERE company_name ILIKE '%laser%'")
print("  consolidated:", [r[0] for r in cur.fetchall()])
cur.execute("SELECT company_name FROM ipo_rhp_intel WHERE company_name ILIKE '%laser%'")
print("  rhp_intel:   ", [r[0] for r in cur.fetchall()])

# 2. does the fuzzy join actually match? run the EXACT join predicate
print("\n=== does fuzzy join match Laser? ===")
cur.execute("""
  SELECT c.company_name, ri.company_name, ri.verdict, ri.one_line
  FROM ipo_consolidated c
  LEFT JOIN ipo_rhp_intel ri ON
    regexp_replace(lower(ri.company_name), '(ltd|limited|and|&)|[^a-z0-9]', '', 'g')
    = regexp_replace(lower(c.company_name), '(ltd|limited|and|&)|[^a-z0-9]', '', 'g')
  WHERE c.company_name ILIKE '%laser%'
""")
for r in cur.fetchall():
    print(f"  IPO='{r[0]}' | RHP matched='{r[1]}' | verdict={r[2]}")

# 3. score/subscription data — is it in now (IPO closed, QIB 56x)?
print("\n=== Laser score + subscription (IPO now closed) ===")
cur.execute("""SELECT company_name, ipo_score, score_band,
  qib_subscription_x, retail_subscription_x, anchor_count, listing_date
  FROM ipo_consolidated WHERE company_name ILIKE '%laser%'""")
for r in cur.fetchall(): print(f"  {r}")
conn.close()
