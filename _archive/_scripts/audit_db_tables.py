#!/usr/bin/env python3
"""READ ONLY — list every table, row count, and whether it feeds the IPO engine.
Proposes drop candidates. Does NOT drop anything — prints SQL for you to review."""
import os,sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import psycopg2
DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn=psycopg2.connect(DB,connect_timeout=25);cur=conn.cursor()
cur.execute("""SELECT table_name FROM information_schema.tables
               WHERE table_schema='public' ORDER BY table_name""")
tables=[r[0] for r in cur.fetchall()]

# tables the IPO engine actively reads (from the routes/scripts we've seen)
IPO_CORE={
 "ipo_consolidated","ipo_intelligence","ipo_rhp_intel","price_candles","delivery_data",
 "ipo_verdicts","ipo_flags","ipo_broker_consensus","ipo_research_notes","platform_config",
 "job_runs","distraction_log","ipo_gmp","access_requests","admin_users",
}
print(f"=== {len(tables)} tables in DB ===\n")
print(f"{'table':<34}{'rows':>10}   status")
print("-"*60)
keep=[];drop=[]
for t in tables:
    try:
        cur.execute(f'SELECT COUNT(*) FROM "{t}"'); n=cur.fetchone()[0]
    except Exception: n=-1
    core = t in IPO_CORE
    (keep if core else drop).append((t,n))
    print(f"{t:<34}{n:>10}   {'✓ IPO-core' if core else '✗ candidate to drop'}")
print(f"\n=== {len(keep)} IPO-core (keep) · {len(drop)} drop candidates ===")
print("\n-- REVIEW these drop candidates. If any is actually used, tell me. --")
print("-- SQL to drop (run ONLY after backup + your review): --\n")
for t,n in drop:
    print(f"-- DROP TABLE IF EXISTS \"{t}\";   -- {n} rows")
conn.close()
