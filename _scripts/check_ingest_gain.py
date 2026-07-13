#!/usr/bin/env python3
"""READ ONLY — coverage after the IPOMatrix ingest + why id-resolution is low."""
import os,sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
import psycopg2
DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn=psycopg2.connect(DB,connect_timeout=25);cur=conn.cursor()
def cov(col):
    cur.execute(f'SELECT COUNT(*),COUNT("{col}") FROM ipo_intelligence WHERE listing_date>=%s',("2016-01-01",))
    t,n=cur.fetchone(); return f"{n}/{t} ({100*n//max(t,1)}%)"
print("Coverage 2016+ after ingest:")
for c in ["price_band_low","ofs_cr","anchor_count","ipo_pe","roe","qib_subscription","listing_close","registrar","promoter_holding_post"]:
    try: print(f"  {c:24} {cov(c)}")
    except Exception as e: print(f"  {c:24} ERR {str(e)[:30]}")
# how many have an nse_symbol at all (resolution needs it)
cur.execute("SELECT COUNT(*) FROM ipo_intelligence WHERE listing_date>='2016-01-01' AND (nse_symbol IS NULL OR nse_symbol='') AND (symbol IS NULL OR symbol='')")
print(f"\n2016+ rows with NO symbol (can't resolve by symbol): {cur.fetchone()[0]}")
conn.close()
