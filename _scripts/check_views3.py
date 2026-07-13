#!/usr/bin/env python3
"""READ ONLY — wave 3 drop candidates. Detects view vs table, emits correct DROP SQL.
Run AFTER PR #106 (dead components) is merged."""
import os,sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import psycopg2
DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn=psycopg2.connect(DB,connect_timeout=25);cur=conn.cursor()
# tables the now-deleted components used (non-IPO)
cands=["annual_financials","quarterly_financials","quarterly_results","valuation","management_commentary",
       "management_commentary_scores","stock_fundamentals","shareholding_history","sector_rotation",
       "technical_signals","earnings_acceleration_scores","multibagger_events","brlm_scores",
       "company_master","amfi_category_flows","amfi_commentary_scores","daily_institutional_flows",
       "alerts","allowed_users","audit_log","intelligence_jobs","price_monthly","subscription_history",
       "user_settings","users","watchlists"]
# only include ones that still exist
cur.execute("SELECT table_name,table_type FROM information_schema.tables WHERE table_schema='public' AND table_name=ANY(%s)",(cands,))
kind={r[0]:r[1] for r in cur.fetchall()}
cur.execute("SELECT matviewname FROM pg_matviews WHERE schemaname='public'")
matv={r[0] for r in cur.fetchall()}
views=[];tables=[];mvs=[]
for c in cands:
    if c not in kind and c not in matv: continue
    if c in matv: mvs.append(c)
    elif kind.get(c)=="VIEW": views.append(c)
    else: tables.append(c)
print("-- WAVE 3 DROP SQL (run after PR #106 merged + build verified) --")
print("-- backup already covers the IPO-core tables; these are non-IPO --")
print("BEGIN;")
for v in views: print(f'DROP VIEW IF EXISTS "{v}" CASCADE;')
for m in mvs:   print(f'DROP MATERIALIZED VIEW IF EXISTS "{m}" CASCADE;')
for t in tables:print(f'DROP TABLE IF EXISTS "{t}" CASCADE;')
print("COMMIT;")
print(f"\n-- {len(tables)} tables, {len(views)} views, {len(mvs)} matviews --")
# what's LEFT after this = the true IPO core
cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'")
print(f"-- DB currently has {cur.fetchone()[0]} objects; after this drop ~{cur.fetchone()[0] if False else 'fewer'} --")
conn.close()
