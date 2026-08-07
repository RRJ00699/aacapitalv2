#!/usr/bin/env python3
"""READ ONLY — are we storing daily candles for the whole 1400-stock universe again?"""
import os,sys,io,time
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import psycopg2
DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
for _ in range(3):
    try: conn=psycopg2.connect(DB,connect_timeout=30,keepalives=1,keepalives_idle=30);break
    except: time.sleep(2)
cur=conn.cursor()

cur.execute("SELECT COUNT(*), COUNT(DISTINCT symbol) FROM price_candles")
rows,syms=cur.fetchone()
print(f"price_candles NOW: {rows:,} rows, {syms:,} distinct symbols")

# how many are IPO symbols vs universe bloat?
cur.execute("""SELECT COUNT(DISTINCT symbol) FROM price_candles WHERE UPPER(symbol) IN
  (SELECT UPPER(COALESCE(symbol_final,nse_symbol,symbol)) FROM ipo_consolidated
   WHERE COALESCE(symbol_final,nse_symbol,symbol) IS NOT NULL)""")
ipo_syms=cur.fetchone()[0]
print(f"  IPO symbols: {ipo_syms}")
print(f"  NON-IPO (universe bloat): {syms-ipo_syms}")

# recent additions — did the last pipeline re-add universe stocks?
cur.execute("SELECT MAX(date) FROM price_candles")
latest=cur.fetchone()[0]
cur.execute("SELECT COUNT(DISTINCT symbol) FROM price_candles WHERE date=%s",(latest,))
recent_syms=cur.fetchone()[0]
print(f"\n  latest date {latest}: {recent_syms} symbols got candles that day")
print(f"  → if ~1400, the universe sync is STILL running (bad)")
print(f"  → if ~{ipo_syms} or fewer, it's IPO-only (good)")
conn.close()
