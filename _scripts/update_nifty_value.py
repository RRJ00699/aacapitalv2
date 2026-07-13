#!/usr/bin/env python3
"""
update_nifty_value.py — store the current Nifty 50 index value into platform_config.
Simple + clean (per spec): the dashboard reads 'nifty_now' for relative strength.
Run daily (or before checking a listing). Uses Kite ltp for the live index value.

  python _scripts/update_nifty_value.py            # via Kite
  python _scripts/update_nifty_value.py --value 24350   # manual set (no Kite needed)
"""
import os,sys,io,argparse,datetime as dt
try: sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
except Exception: pass
import psycopg2

def get_nifty_via_kite():
    try:
        from kiteconnect import KiteConnect
    except ImportError:
        return None
    # token flow reused from kite_connect.py conventions
    ak=os.environ.get("KITE_API_KEY"); tok=os.environ.get("KITE_ACCESS_TOKEN")
    if not ak or not tok: return None
    try:
        k=KiteConnect(api_key=ak); k.set_access_token(tok)
        q=k.ltp(["NSE:NIFTY 50"])
        return float(q["NSE:NIFTY 50"]["last_price"])
    except Exception as e:
        print("kite fetch failed:",str(e)[:60]); return None

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--value",type=float,help="set Nifty value manually")
    a=ap.parse_args()
    val=a.value if a.value else get_nifty_via_kite()
    if not val:
        sys.exit("No Nifty value — pass --value N, or set KITE_API_KEY/KITE_ACCESS_TOKEN.")
    DB=os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    conn=psycopg2.connect(DB,connect_timeout=25);cur=conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS platform_config (key TEXT PRIMARY KEY, value TEXT)""")
    now=dt.datetime.utcnow().isoformat()
    for k,v in [("nifty_now",str(val)),("nifty_updated",now)]:
        cur.execute("""INSERT INTO platform_config(key,value) VALUES(%s,%s)
                       ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value""",(k,v))
    conn.commit()
    print(f"nifty_now = {val} (updated {now})")
    conn.close()

if __name__=="__main__": main()
