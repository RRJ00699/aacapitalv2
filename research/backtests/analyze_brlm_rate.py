#!/usr/bin/env python3
"""READ ONLY — BRLM junk RATE (not count). Which lead managers have a HIGH % of junk?"""
import os,sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import psycopg2
DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn=psycopg2.connect(DB,connect_timeout=25);cur=conn.cursor()

# junk RATE per lead BRLM (only those with >=5 total IPOs, so rates are meaningful)
cur.execute("""
  WITH lead AS (
    SELECT TRIM(SPLIT_PART(c.brlm_names,',',1)) AS brlm, v.verdict
    FROM ipo_consolidated c JOIN ipo_verdicts v ON v.company_name=c.company_name
    WHERE c.brlm_names IS NOT NULL AND TRIM(c.brlm_names) <> '' AND c.brlm_names <> 'nan'
  )
  SELECT brlm,
         COUNT(*) AS total,
         SUM(CASE WHEN verdict IN ('AVOID','CAUTION') THEN 1 ELSE 0 END) AS junkish,
         ROUND(100.0*SUM(CASE WHEN verdict IN ('AVOID','CAUTION') THEN 1 ELSE 0 END)/COUNT(*),0) AS junk_pct,
         SUM(CASE WHEN verdict='TRADE' THEN 1 ELSE 0 END) AS trade_n
  FROM lead GROUP BY brlm HAVING COUNT(*)>=5
  ORDER BY junk_pct DESC, total DESC LIMIT 25
""")
print("=== BRLM junk RATE (>=5 IPOs) — HIGH junk%% = real red flag ===")
print(f"  {'BRLM':34} {'tot':>4} {'junk%':>6} {'TRADE':>6}")
for brlm,total,junkish,pct,trade in cur.fetchall():
    flag=" 🔴" if pct>=80 else (" 🟡" if pct>=65 else "")
    print(f"  {(brlm or '')[:34]:34} {total:>4} {int(pct):>5}%% {trade:>6}{flag}")

# the BEST BRLMs (highest TRADE rate)
cur.execute("""
  WITH lead AS (
    SELECT TRIM(SPLIT_PART(c.brlm_names,',',1)) AS brlm, v.verdict
    FROM ipo_consolidated c JOIN ipo_verdicts v ON v.company_name=c.company_name
    WHERE c.brlm_names IS NOT NULL AND TRIM(c.brlm_names) <> '' AND c.brlm_names <> 'nan'
  )
  SELECT brlm, COUNT(*) AS total,
         ROUND(100.0*SUM(CASE WHEN verdict='TRADE' THEN 1 ELSE 0 END)/COUNT(*),0) AS trade_pct
  FROM lead GROUP BY brlm HAVING COUNT(*)>=5
  ORDER BY trade_pct DESC, total DESC LIMIT 12
""")
print("\n=== BEST BRLMs (highest TRADE rate, >=5 IPOs) ===")
for brlm,total,pct in cur.fetchall():
    print(f"  {(brlm or '')[:34]:34} {total:>4} IPOs, {int(pct)}% TRADE")
conn.close()
