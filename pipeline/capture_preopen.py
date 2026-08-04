#!/usr/bin/env python3
"""Bounded, forward-only listing-day capture into existing listing_observations."""
import argparse, datetime as dt, json, os, time
from zoneinfo import ZoneInfo
import psycopg2
from _scripts.kite_connect import get_kite
from config import (MIN_POSITIVE_LIMIT, PREOPEN_DEFAULT_IPOS, PREOPEN_HARD_MAX_IPOS,
    PREOPEN_DEFAULT_RETRIES, PREOPEN_HARD_MAX_RETRIES, WEEKDAY_MAX_INDEX,
    PREOPEN_START_MINUTE_IST, PREOPEN_END_MINUTE_IST)

def capture(now=None, limit=PREOPEN_DEFAULT_IPOS, dry_run=False, retries=PREOPEN_DEFAULT_RETRIES):
    limit=max(MIN_POSITIVE_LIMIT,min(limit,PREOPEN_HARD_MAX_IPOS)); retries=max(0,min(retries,PREOPEN_HARD_MAX_RETRIES))
    now=now or dt.datetime.now(ZoneInfo("Asia/Kolkata")); minute=now.hour*60+now.minute
    if now.weekday()>WEEKDAY_MAX_INDEX or not PREOPEN_START_MINUTE_IST<=minute<=PREOPEN_END_MINUTE_IST:
      print("ineligible: outside weekday 08:55-10:05 IST"); return 0
    conn=psycopg2.connect(os.environ["DATABASE_URL"]); cur=conn.cursor()
    # ISIN is selected first and is the durable identity; symbol is only Kite routing metadata.
    cur.execute("""SELECT i.id, i.name, i.isin, UPPER(i.symbol), i.listing_date,
        'IST-today mainboard listing with ISIN and symbol' AS reason_selected,
        ii.issue_size_cr
      FROM ipo i LEFT JOIN ipo_issue ii ON ii.ipo_id=i.id
      WHERE i.listing_date=%s AND i.isin IS NOT NULL
      AND i.symbol IS NOT NULL AND i.is_mainboard=true
      ORDER BY CASE WHEN COALESCE(ii.issue_size_cr,0) >= 150 THEN 0 ELSE 1 END,
        ii.issue_size_cr DESC NULLS LAST, i.id
      LIMIT %s""",(now.date(),limit+MIN_POSITIVE_LIMIT))
    targets=cur.fetchall(); cur.close(); conn.close()
    if not targets:
      print(json.dumps({"selected":[],"selected_isins":[],"reason":"no listing-day IPO exists","fast_exit":True,"dry_run":dry_run,"limit":limit}))
      return 0
    if len(targets)>limit: print(f"bounded: {len(targets)} eligible exceeds limit {limit}"); targets=targets[:limit]
    selected=[{"ipo_name":x[1],"isin":x[2],"symbol":x[3],"listing_date":str(x[4]),"reason_selected":x[5],"issue_size_cr":float(x[6]) if x[6] is not None else None} for x in targets]
    print(json.dumps({"dry_run":dry_run,"selected":selected,"selected_isins":[x["isin"] for x in selected],"limit":limit,"obs_type":"preopen",
      "columns":["ipo_id","observed_at","obs_type","ltp","buy_qty","sell_qty","payload"],"idempotency":"(ipo_id,obs_type,observed_at)","expected_rows":len(targets)}))
    if dry_run or not targets: return 0
    kite=get_kite(); conn=psycopg2.connect(os.environ["DATABASE_URL"]); cur=conn.cursor(); count=0
    for ipo_id,_name,isin,symbol,_listing_date,_reason,_issue_size_cr in targets:
      quote=None
      for attempt in range(retries+MIN_POSITIVE_LIMIT):
        try: quote=kite.quote([f"NSE:{symbol}"]).get(f"NSE:{symbol}",{}); break
        except Exception:
          if attempt==retries: raise
          time.sleep(2**attempt)
      buy,sell=int(quote.get("buy_quantity") or 0),int(quote.get("sell_quantity") or 0)
      payload={"isin":isin,"symbol":symbol,"discovery_price":quote.get("ohlc",{}).get("open") or quote.get("last_price"),"depth":quote.get("depth")}
      observed=now.replace(second=0,microsecond=0)
      cur.execute("""INSERT INTO listing_observations (ipo_id,observed_at,obs_type,ltp,buy_qty,sell_qty,payload)
        VALUES(%s,%s,'preopen',%s,%s,%s,%s::jsonb) ON CONFLICT (ipo_id,obs_type,observed_at) DO NOTHING""",
        (ipo_id,observed,quote.get("last_price"),buy,sell,json.dumps(payload))); count+=cur.rowcount
    conn.commit(); cur.close(); conn.close(); print(f"captured {count}"); return count

if __name__=="__main__":
 ap=argparse.ArgumentParser(); ap.add_argument("--limit",type=int,default=PREOPEN_DEFAULT_IPOS); ap.add_argument("--dry-run",action="store_true"); ap.add_argument("--retries",type=int,default=PREOPEN_DEFAULT_RETRIES); a=ap.parse_args(); capture(limit=a.limit,dry_run=a.dry_run,retries=a.retries)
