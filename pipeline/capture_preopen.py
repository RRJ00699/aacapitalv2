#!/usr/bin/env python3
"""Forward-only listing pre-open capture: Kite -> listing_observations.

Run every five minutes; outside 08:55-10:05 IST it exits without network work.
The UNIQUE key makes retries safe.  This service replaces the deleted
ipo_preopen_book write and deliberately has no dependency on a browser request.
"""
import datetime as dt, json, os, psycopg2
from zoneinfo import ZoneInfo
from _scripts.kite_connect import get_kite

def capture(now=None):
    now = now or dt.datetime.now(ZoneInfo("Asia/Kolkata"))
    minute = now.hour * 60 + now.minute
    if now.weekday() > 4 or not 8 * 60 + 55 <= minute <= 10 * 60 + 5:
        print("outside listing capture window"); return 0
    conn = psycopg2.connect(os.environ["DATABASE_URL"]); cur = conn.cursor()
    cur.execute("SELECT id, UPPER(symbol) FROM ipo WHERE listing_date=%s AND symbol IS NOT NULL AND is_mainboard=true", (now.date(),))
    targets = cur.fetchall(); kite = get_kite(); count = 0
    for ipo_id, symbol in targets:
        quote = kite.quote([f"NSE:{symbol}"]).get(f"NSE:{symbol}", {})
        buy, sell = int(quote.get("buy_quantity") or 0), int(quote.get("sell_quantity") or 0)
        payload = {"discovery_price": quote.get("ohlc", {}).get("open") or quote.get("last_price"), "depth": quote.get("depth")}
        observed = now.replace(second=0, microsecond=0)
        cur.execute("""INSERT INTO listing_observations
          (ipo_id,observed_at,obs_type,ltp,buy_qty,sell_qty,payload)
          VALUES(%s,%s,'preopen',%s,%s,%s,%s::jsonb)
          ON CONFLICT (ipo_id,obs_type,observed_at) DO NOTHING""",
          (ipo_id, observed, quote.get("last_price"), buy, sell, json.dumps(payload)))
        count += cur.rowcount
    conn.commit(); cur.close(); conn.close(); print(f"captured {count} preopen observation(s)"); return count

if __name__ == "__main__": capture()
