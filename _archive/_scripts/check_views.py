#!/usr/bin/env python3
"""READ ONLY — for each drop candidate, is it a TABLE or a VIEW? Emits correct DROP SQL."""
import os,sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import psycopg2
DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn=psycopg2.connect(DB,connect_timeout=25);cur=conn.cursor()
cands=["backtest_runs","backtest_trades","bulk_deals","convergence_history","convergence_ranking","earnings_events","earnings_signals","earnings_surprise","engine_correction_reports","financial_dna","institutional_large_deals","latest_amfi_liquidity_score","latest_earnings_acceleration","latest_management_commentary","latest_management_commentary_score","mf_conviction_flags","mf_scheme_holdings","mf_stock_summary","multibagger_similarity","ownership_signals","price_alerts","price_candles_weekly","smart_money_summary","technical_features","thesis_notes","trade_journal","transcript_documents","transcript_intelligence","watchlist_stocks","weekly_dna"]
cur.execute("""SELECT table_name, table_type FROM information_schema.tables
               WHERE table_schema='public' AND table_name = ANY(%s)""",(cands,))
kind={r[0]:r[1] for r in cur.fetchall()}
# also check materialized views (not in information_schema.tables)
cur.execute("SELECT matviewname FROM pg_matviews WHERE schemaname='public'")
matviews={r[0] for r in cur.fetchall()}
tables=[]; views=[]; matvs=[]
for c in cands:
    if c in matviews: matvs.append(c)
    elif kind.get(c)=="VIEW": views.append(c)
    else: tables.append(c)
print("-- Correct DROP SQL by object type --")
print("BEGIN;")
for v in views:  print(f'DROP VIEW IF EXISTS "{v}" CASCADE;')
for m in matvs:  print(f'DROP MATERIALIZED VIEW IF EXISTS "{m}" CASCADE;')
for t in tables: print(f'DROP TABLE IF EXISTS "{t}" CASCADE;')
print("COMMIT;")
print(f"\n-- {len(tables)} tables, {len(views)} views, {len(matvs)} matviews --")
conn.close()
