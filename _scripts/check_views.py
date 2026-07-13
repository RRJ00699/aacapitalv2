#!/usr/bin/env python3
"""READ ONLY — for each drop candidate, is it a TABLE or a VIEW? Emits correct DROP SQL."""
import os,sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import psycopg2
DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn=psycopg2.connect(DB,connect_timeout=25);cur=conn.cursor()
cands=["anchor_deal_signals","anchor_investor_master","earnings_estimates","financial_dna_history","institutional_flow_flags","instrument_master","ipo_active","ipo_anchor_history","ipo_backtest_results","ipo_historical_results","ipo_listed_performance","ipo_listing_signals","ipo_momentum","ipo_rhp_flags","ipo_sbi_signals","ipo_similarity_matches","ipo_subscription_history","ipo_subscription_snapshot","isin_symbol_map","management_commentary_normalized","management_quality_history","ml_model_registry","multibagger_patterns","nifty_monthly","nse_shareholding_filings_raw","order_book_signals","order_book_summary","stock_quality_flags","system_health","technical_indicators_daily","technical_indicators_monthly","technical_indicators_weekly"]
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
