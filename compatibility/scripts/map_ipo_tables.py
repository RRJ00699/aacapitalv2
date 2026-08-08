#!/usr/bin/env python3
"""READ ONLY — map the 21 IPO tables: row counts, key columns, overlap. Find redundancy."""
import os,sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import psycopg2
DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn=psycopg2.connect(DB,connect_timeout=25);cur=conn.cursor()

ipo_tables=["ipo_consolidated","ipo_intelligence","ipo_rhp_intel","ipo_gmp","ipo_verdicts",
  "ipo_flags","ipo_master","ipo_history","ipo_live","ipo_daily_levels","ipo_predictions",
  "ipo_tick_feed","ipo_issue_details","ipo_similarity_results","ipo_accuracy_leaderboard",
  "ipo_broker_consensus","ipo_research_notes","ipo_intelligence_backup_20260707"]

print("=== IPO TABLE MAP ===")
info={}
for t in ipo_tables:
    try:
        cur.execute(f"SELECT COUNT(*) FROM {t}"); n=cur.fetchone()[0]
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s ORDER BY ordinal_position",(t,))
        cols=[r[0] for r in cur.fetchall()]
        info[t]=(n,cols)
        keycols=[c for c in cols if any(k in c.lower() for k in ["company","symbol","name","id","date"])][:5]
        print(f"  {t:38} {n:>7,} rows, {len(cols):>3} cols | keys: {', '.join(keycols[:4])}")
    except Exception as e:
        print(f"  {t:38} (err: {str(e)[:35]})")

# find tables with heavy column overlap (candidate merges)
print("\n=== COLUMN OVERLAP (candidate redundancy) ===")
names=list(info.keys())
for i in range(len(names)):
    for j in range(i+1,len(names)):
        a,b=names[i],names[j]
        ca,cb=set(info[a][1]),set(info[b][1])
        shared=ca&cb
        # ignore trivial shared (id, created_at)
        meaningful=shared-{"id","created_at","updated_at"}
        if len(meaningful)>=5:
            pct=100*len(meaningful)//min(len(ca),len(cb))
            print(f"  {a} ∩ {b}: {len(meaningful)} shared cols ({pct}% of smaller) → possible merge")
conn.close()
