#!/usr/bin/env python3
"""
ipo_tick_capture.py — capture live ticks for IPOs listing TODAY -> ipo_tick_feed.
Schedule at 09:14 IST on trading days; streams until 15:35 IST.

Kite honors a websocket ~6h and the daily session is ~6h15m, so a socket held all
day can drop mid-session. This runs as a SUPERVISOR that spawns a fresh single-socket
WORKER every ~4h. New process = fresh Twisted reactor (pykiteconnect can't restart a
stopped reactor in-process) + freshly re-read token from platform_config. So no socket
nears the 6h ceiling, and a drop is logged (on_close/on_error), never silent. Exits
cleanly at 15:35 IST. Cron line is unchanged (no args = supervisor).

  supervisor:  python _scripts/ipo_tick_capture.py
  worker:      python _scripts/ipo_tick_capture.py --until 2025-07-04T13:14:00+05:30
Needs a valid Kite token (platform_config).
"""
import os, sys, datetime, time, argparse, subprocess
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,HERE)
try:
    from zoneinfo import ZoneInfo; IST=ZoneInfo("Asia/Kolkata")
except Exception:
    IST=None
RECYCLE_SECONDS=4*3600   # rebuild the socket every 4h, well under Kite's ~6h honor window

def _now(): return datetime.datetime.now(IST) if IST else datetime.datetime.now()

def _listers(cur, today):
    cur.execute("SELECT nse_symbol FROM ipo_intelligence WHERE listing_date=%s AND nse_symbol IS NOT NULL",(today,))
    return [r[0] for r in cur.fetchall()]

def worker(until):
    import psycopg2
    from kite_connect import get_kite
    try: from kiteconnect import KiteTicker
    except ImportError: sys.exit("pip install kiteconnect --break-system-packages")
    DB=os.getenv("DATABASE_URL"); conn=psycopg2.connect(DB); cur=conn.cursor()
    today=_now().date()
    syms=_listers(cur, today)
    if not syms: print("worker: no listers; exit."); return
    kite=get_kite(); inst={i["tradingsymbol"]:i["instrument_token"] for i in kite.instruments("NSE")}
    tok2sym={inst[s]:s for s in syms if s in inst}
    if not tok2sym: print("worker: listers not in NSE instruments yet; exit."); return
    cur.execute("""CREATE TABLE IF NOT EXISTS ipo_tick_feed(
        symbol text, ts timestamptz, ltp numeric, qty numeric, vol numeric,
        bid numeric, ask numeric, PRIMARY KEY(symbol,ts))"""); conn.commit()

    def on_ticks(ws,ticks):
        rows=[]
        for t in ticks:
            s=tok2sym.get(t["instrument_token"])
            if not s: continue
            d=t.get("depth",{})
            rows.append((s,_now(),t.get("last_price"),t.get("last_traded_quantity"),t.get("volume_traded"),
                         (d.get("buy") or [{}])[0].get("price"),(d.get("sell") or [{}])[0].get("price")))
        if rows:
            try:
                cur.executemany("""INSERT INTO ipo_tick_feed(symbol,ts,ltp,qty,vol,bid,ask)
                    VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(symbol,ts) DO NOTHING""",rows); conn.commit()
            except Exception as e:
                conn.rollback(); print(f"db write skipped: {e}")
    def on_connect(ws,resp): ws.subscribe(list(tok2sym)); ws.set_mode(ws.MODE_FULL,list(tok2sym)); print("subscribed.")
    def on_close(ws,code,reason): print(f"ws closed ({code}): {reason}")
    def on_error(ws,code,reason): print(f"ws error ({code}): {reason}")

    kt=KiteTicker(os.getenv("KITE_API_KEY") or getattr(kite,"api_key","br9m41pn8nvvywnl"), kite.access_token)
    kt.on_ticks=on_ticks; kt.on_connect=on_connect; kt.on_close=on_close; kt.on_error=on_error
    kt.connect(threaded=True)
    while _now() < until: time.sleep(15)
    try: kt.close()
    except Exception: pass
    print("worker: cycle done.")

def supervisor():
    import psycopg2
    DB=os.getenv("DATABASE_URL"); conn=psycopg2.connect(DB); cur=conn.cursor()
    today=_now().date(); syms=_listers(cur, today); conn.close()
    if not syms: print(f"no IPOs listing {today} — nothing to capture."); return
    print(f"listing today: {syms}")
    end=_now().replace(hour=15,minute=35,second=0,microsecond=0)
    while _now() < end:
        cycle_end=min(end, _now()+datetime.timedelta(seconds=RECYCLE_SECONDS))
        print(f"spawning worker until {cycle_end:%H:%M:%S}")
        subprocess.run([sys.executable, os.path.abspath(__file__), "--until", cycle_end.isoformat()])
        if _now() < end: time.sleep(2)   # guard so a fast-failing worker can't spin hot
    print("capture window closed.")

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--until"); a=ap.parse_args()
    if a.until: worker(datetime.datetime.fromisoformat(a.until))
    else: supervisor()

if __name__=="__main__": main()
