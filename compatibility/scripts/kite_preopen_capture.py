#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kite_preopen_capture.py — pre-open order book via ZERODHA, not NSE.

WHY THIS EXISTS (2026-07-19): NSE's own endpoints are BLOCKED from the VM —
Akamai rejects the Hetzner datacenter IP in ~42ms (403 with a browser UA, 000
without). Even curl_cffi with a Chrome fingerprint times out. Verified against
www.nseindia.com and every /api/ path.

But Kite works fine from the VM (the token refresh has run there for weeks), and
`kite.quote()` returns the SAME data during the special pre-open session:
    depth.buy[5] / depth.sell[5]  -> the order book
    last_price                    -> IEP (indicative equilibrium price)
    total_buy_quantity / total_sell_quantity
So the pre-open book is reachable through the broker we already pay for.

Writes to ipo_preopen_book with source='kite-live' so it never mixes with
NSE-sourced rows. Content-hash dedupe: only CHANGED book states insert.

Run:  python _scripts/kite_preopen_capture.py --once      # one poll, any time
      python _scripts/kite_preopen_capture.py             # full window (cron)
      python _scripts/kite_preopen_capture.py --symbols ALPINE,SBIFUND
"""
import argparse, datetime as dt, hashlib, json, os, sys, time

POLL_S = 15
WINDOW_START = (8, 57)     # IST — pre-open opens 09:00
WINDOW_END   = (10, 20)    # covers the 10:13-10:16 band the owner cares about

def ist_now():
    return dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=5, minutes=30)

def in_window(t):
    a = t.replace(hour=WINDOW_START[0], minute=WINDOW_START[1], second=0, microsecond=0)
    b = t.replace(hour=WINDOW_END[0],   minute=WINDOW_END[1],   second=0, microsecond=0)
    return a <= t <= b

def parse_quote(sym, q):
    """Kite quote -> the same shape nse_preopen_capture produces."""
    depth = (q.get("depth") or {})
    buys, sells = depth.get("buy") or [], depth.get("sell") or []
    bb = max((l for l in buys if l.get("quantity")), key=lambda l: l["price"], default=None)
    ba = min((l for l in sells if l.get("quantity")), key=lambda l: l["price"], default=None)
    bq, sq = q.get("buy_quantity"), q.get("sell_quantity")
    lean = round((bq - sq) / sq * 100, 1) if (bq and sq and sq > 0) else None
    rec = {"symbol": sym, "iep": q.get("last_price"),
           "ieq": q.get("last_quantity") or q.get("volume"),
           "buy_qty": bq, "sell_qty": sq, "lean_pct": lean,
           "best_bid": bb["price"] if bb else None,
           "best_bid_qty": bb["quantity"] if bb else None,
           "best_ask": ba["price"] if ba else None,
           "best_ask_qty": ba["quantity"] if ba else None,
           "cancelled_qty": None, "raw": q}
    rec["state_hash"] = hashlib.md5(
        f"{sym}|{rec['iep']}|{bq}|{sq}|{rec['best_bid']}|{rec['best_ask']}".encode()).hexdigest()
    return rec

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--symbols", help="comma-separated NSE symbols (default: today's listings)")
    a = ap.parse_args()

    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"]); cur = conn.cursor()

    if a.symbols:
        want = [s.strip().upper() for s in a.symbols.split(",")]
    else:
        cur.execute("""SELECT UPPER(COALESCE(NULLIF(nse_symbol,''), symbol))
                       FROM ipo_intelligence
                       WHERE listing_date = (now() AT TIME ZONE 'Asia/Kolkata')::date
                         AND COALESCE(NULLIF(nse_symbol,''), symbol) IS NOT NULL""")
        want = [r[0] for r in cur.fetchall()]
    if not want:
        print("no mainboard IPO lists today — exit."); return
    print(f"kite pre-open capture: {want}")

    from kiteconnect import KiteConnect
    cur.execute("SELECT value FROM platform_config WHERE key='kite_access_token'")
    row = cur.fetchone()
    if not row: sys.exit("no kite_access_token in platform_config — run refresh_kite_token.py")
    kite = KiteConnect(api_key=os.environ.get("KITE_API_KEY", ""))
    kite.set_access_token(row[0])

    instruments = [f"NSE:{s}" for s in want]
    seen = 0
    while True:
        t = ist_now()
        if not a.once and not in_window(t):
            if (t.hour, t.minute) > WINDOW_END: print("window closed — exit."); break
            time.sleep(20); continue
        try:
            data = kite.quote(instruments)
            for key, q in data.items():
                sym = key.split(":")[-1]
                rec = parse_quote(sym, q)
                cur.execute("""INSERT INTO ipo_preopen_book
                    (symbol, discovery_price, buy_qty, sell_qty, lean_pct, source,
                     ieq, best_bid, best_bid_qty, best_ask, best_ask_qty, state_hash)
                    VALUES (%s,%s,%s,%s,%s,'kite-live',%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (state_hash) DO NOTHING""",
                    (rec["symbol"], rec["iep"], rec["buy_qty"], rec["sell_qty"], rec["lean_pct"],
                     rec["ieq"], rec["best_bid"], rec["best_bid_qty"],
                     rec["best_ask"], rec["best_ask_qty"], rec["state_hash"]))
                if cur.rowcount: seen += 1
                print(f"{t:%H:%M:%S} {sym}: iep={rec['iep']} bid={rec['best_bid']}x{rec['best_bid_qty']} "
                      f"ask={rec['best_ask']}x{rec['best_ask_qty']} lean={rec['lean_pct']}%")
            conn.commit()
        except Exception as e:
            print(f"poll error: {str(e)[:160]}")
            time.sleep(20)
        if a.once: break
        time.sleep(POLL_S)
    print(f"done — {seen} new book states written (source='kite-live')")
    conn.close()

if __name__ == "__main__":
    main()
