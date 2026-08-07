#!/usr/bin/env python3
"""READ ONLY — which table has the fair-value columns (consolidated vs intelligence)?"""
import os,sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import psycopg2
DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn=psycopg2.connect(DB,connect_timeout=25);cur=conn.cursor()
fv=["ipo_pe","eps_post","eps_pre","peer_median_pe","roe","revenue_cagr_3y","profit_cagr_3y","debt_equity","ofs_pct","fresh_issue_ratio","issue_price","structure_type"]
for tbl in ["ipo_consolidated","ipo_intelligence"]:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s",(tbl,))
    cols=set(r[0] for r in cur.fetchall())
    have=[c for c in fv if c in cols]
    print(f"{tbl}: has {have}")
# also — is issue_price on consolidated? and a sample for a scored IPO
cur.execute("""SELECT company_name, issue_price, ipo_pe, peer_median_pe, roe, revenue_cagr_3y, debt_equity, ofs_pct, structure_type
  FROM ipo_consolidated WHERE ipo_pe IS NOT NULL AND peer_median_pe IS NOT NULL LIMIT 3""")
print("\n=== sample IPOs with fair-value inputs ===")
for r in cur.fetchall(): print(f"  {r}")
conn.close()
