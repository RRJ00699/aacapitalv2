#!/usr/bin/env python3
"""
ipo_tick_capture.py — auto-capture live ticks for IPOs listing TODAY → ipo_tick_feed.
Schedule at 09:14 on trading days; it subscribes to today's listers and streams until 15:35.
Feeds the live floor/ceiling (ipo_level_analysis via analyze_listing_day.py).

  python _scripts\\ipo_tick_capture.py
Schedule: schtasks /create /tn "AAC IPO Ticks" /tr "python C:\\aacapital-v2\\_scripts\\ipo_tick_capture.py" /sc daily /st 09:14
Needs a valid Kite token (platform_config).
"""
import os, sys, datetime, time
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,HERE)

def main():
    import psycopg2
    from kite_connect import get_kite
    try: from kiteconnect import KiteTicker
    except ImportError: sys.exit("pip install kiteconnect --break-system-packages")

    DB=os.getenv("DATABASE_URL"); conn=psycopg2.connect(DB); cur=conn.cursor()
    today=datetime.date.today()
    cur.execute("SELECT nse_symbol FROM ipo_intelligence WHERE listing_date=%s AND nse_symbol IS NOT NULL",(today,))
    syms=[r[0] for r in cur.fetchall()]
    if not syms: print(f"no IPOs listing {today} — nothing to capture."); return
    print(f"listing today: {syms}")

    kite=get_kite(); inst={i["tradingsymbol"]:i["instrument_token"] for i in kite.instruments("NSE")}
    tok2sym={inst[s]:s for s in syms if s in inst}
    if not tok2sym: print("none of today's listers found in NSE instruments yet."); return

    cur.execute("""CREATE TABLE IF NOT EXISTS ipo_tick_feed(
        symbol text, ts timestamptz, ltp numeric, qty numeric, vol numeric,
        bid numeric, ask numeric, PRIMARY KEY(symbol,ts))""")
    kt=KiteTicker(os.getenv("KITE_API_KEY") or getattr(kite,"api_key",None), kite.access_token)

    def on_ticks(ws,ticks):
        rows=[]
        for t in ticks:
            s=tok2sym.get(t["instrument_token"])
            if not s: continue
            d=t.get("depth",{})
            rows.append((s, datetime.datetime.now(), t.get("last_price"),
                         t.get("last_traded_quantity"), t.get("volume_traded"),
                         (d.get("buy") or [{}])[0].get("price"), (d.get("sell") or [{}])[0].get("price")))
        if rows:
            cur.executemany("""INSERT INTO ipo_tick_feed(symbol,ts,ltp,qty,vol,bid,ask)
                VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(symbol,ts) DO NOTHING""",rows)
            conn.commit()
    def on_connect(ws,resp): ws.subscribe(list(tok2sym)); ws.set_mode(ws.MODE_FULL,list(tok2sym)); print("subscribed.")
    kt.on_ticks=on_ticks; kt.on_connect=on_connect
    kt.connect(threaded=True)
    end=datetime.datetime.now().replace(hour=15,minute=35,second=0)
    while datetime.datetime.now()<end: time.sleep(30)
    kt.close(); print("capture window closed.")

if __name__=="__main__": main()
