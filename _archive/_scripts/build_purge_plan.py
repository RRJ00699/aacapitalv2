#!/usr/bin/env python3
"""READ ONLY — measures bloat + EMITS the purge SQL (you review + run it). Drops nothing itself."""
import os,sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import psycopg2
def _has(cur,t,c):
    cur.execute("SELECT 1 FROM information_schema.columns WHERE table_name=%s AND column_name=%s",(t,c));return bool(cur.fetchone())
DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn=psycopg2.connect(DB,connect_timeout=25);cur=conn.cursor()

def count(sql,args=None):
    cur.execute(sql,args or []); return cur.fetchone()[0]

print("=== CURRENT SIZES ===")
for t in ["price_candles","delivery_data","job_runs","market_regimes","audit_log","market_snapshot","institutional_large_deals"]:
    try:
        n=count(f"SELECT COUNT(*) FROM {t}")
        print(f"  {t:28} {n:>10,} rows")
    except Exception as e:
        print(f"  {t:28} (missing/err: {str(e)[:30]})")

# IPO symbol set (for candle + delivery trimming)
ipo_sym_sql = """UPPER(COALESCE(symbol_final,nse_symbol,symbol)) FROM ipo_consolidated
                 WHERE COALESCE(symbol_final,nse_symbol,symbol) IS NOT NULL"""

print("\n=== BLOAT MEASUREMENT ===")
pc_nonipo=count(f"SELECT COUNT(*) FROM price_candles WHERE UPPER(symbol) NOT IN (SELECT {ipo_sym_sql})")
dd_nonipo=count(f"SELECT COUNT(*) FROM delivery_data WHERE UPPER(symbol) NOT IN (SELECT {ipo_sym_sql})")
jr_old=count("SELECT COUNT(*) FROM job_runs WHERE requested_at < NOW() - INTERVAL '30 days'") if _has(cur,"job_runs","requested_at") else 0
print(f"  price_candles non-IPO rows:  {pc_nonipo:>10,}")
print(f"  delivery_data non-IPO rows:  {dd_nonipo:>10,}")

print("\n" + "="*60)
print("-- REVIEW, THEN RUN. Trims bloat; keeps IPO + recent data. --")
print("="*60)
print("BEGIN;")
print(f"-- 1. price_candles: keep only IPO symbols (drops {pc_nonipo:,} non-IPO rows)")
print(f"DELETE FROM price_candles WHERE UPPER(symbol) NOT IN (SELECT {ipo_sym_sql.strip()});")
print(f"-- 2. delivery_data: keep only IPO symbols (drops {dd_nonipo:,} non-IPO rows)")
print(f"DELETE FROM delivery_data WHERE UPPER(symbol) NOT IN (SELECT {ipo_sym_sql.strip()});")
print("-- 3. job_runs: keep last 30 days")
print("DELETE FROM job_runs WHERE requested_at < NOW() - INTERVAL '30 days';")
print("-- 4. audit_log: keep last 90 days")
print("DELETE FROM audit_log WHERE created_at < NOW() - INTERVAL '90 days';")
print("-- 5. institutional_large_deals: non-IPO, nothing reads it -> DROP")
print('DROP TABLE IF EXISTS institutional_large_deals CASCADE;')
print("COMMIT;")
print("-- (market_snapshot + market_regimes left alone — live/small)")
conn.close()
