#!/usr/bin/env python3
"""READ ONLY — what's actually in price_candles? IPO symbols vs full universe."""
import os,sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import psycopg2
DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn=psycopg2.connect(DB,connect_timeout=25);cur=conn.cursor()

cur.execute("SELECT COUNT(*), COUNT(DISTINCT symbol) FROM price_candles")
rows,syms=cur.fetchone()
print(f"price_candles: {rows:,} rows across {syms:,} distinct symbols")

# how many of those symbols are actual IPOs (in ipo_consolidated)?
cur.execute("""
  SELECT COUNT(DISTINCT pc.symbol)
  FROM price_candles pc
  WHERE UPPER(pc.symbol) IN (
    SELECT UPPER(COALESCE(symbol_final, nse_symbol, symbol)) FROM ipo_consolidated
    WHERE COALESCE(symbol_final, nse_symbol, symbol) IS NOT NULL
  )
""")
ipo_syms=cur.fetchone()[0]
print(f"  of which ARE IPO symbols: {ipo_syms:,}")
print(f"  NON-IPO symbols (full-universe bloat): {syms-ipo_syms:,}")

# rows for non-IPO symbols = wasted
cur.execute("""
  SELECT COUNT(*)
  FROM price_candles pc
  WHERE UPPER(pc.symbol) NOT IN (
    SELECT UPPER(COALESCE(symbol_final, nse_symbol, symbol)) FROM ipo_consolidated
    WHERE COALESCE(symbol_final, nse_symbol, symbol) IS NOT NULL
  )
""")
waste=cur.fetchone()[0]
print(f"  NON-IPO rows (could purge): {waste:,} ({100*waste//rows}%)")

# date range
cur.execute("SELECT MIN(date), MAX(date) FROM price_candles")
lo,hi=cur.fetchone()
print(f"  date range: {lo} .. {hi}")
conn.close()
