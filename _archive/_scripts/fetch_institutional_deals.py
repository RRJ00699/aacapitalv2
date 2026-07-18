#!/usr/bin/env python3
"""
fetch_institutional_deals.py — pulls today's NSE bulk + block deals (real institutional
buy/sell activity by client name) into institutional_large_deals. Complements the
quarterly smart_money trend with a recent, event-driven signal.

Productionized from the working standalone version: adds block deals (not just bulk),
auto-creates the table, and is idempotent (ON CONFLICT DO NOTHING) so re-runs in the
same day don't duplicate.

NOTE: NSE's JSON field names occasionally differ by endpoint. The mapping below matches
the snapshot-capital-market-largedeal feed; if a run inserts 0 rows, print one raw record
(uncomment the debug line) and adjust the keys.

Run:  python _scripts/fetch_institutional_deals.py
Env:  DATABASE_URL (or NEON_DATABASE_URL)
"""
import os, sys, time, requests, psycopg2
from psycopg2.extras import execute_values
from datetime import datetime

URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
if not URL:
    sys.exit("DATABASE_URL not set")

SNAPSHOT = "https://www.nseindia.com/api/snapshot-capital-market-largedeal"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.nseindia.com/market-data/large-deals",
    "Connection": "keep-alive",
}


def ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS institutional_large_deals (
            id SERIAL PRIMARY KEY,
            deal_date DATE NOT NULL,
            ticker TEXT NOT NULL,
            client_name TEXT,
            deal_type TEXT,            -- BULK | BLOCK
            transaction_type TEXT,     -- BUY | SELL
            quantity BIGINT,
            trade_price NUMERIC(14,2),
            UNIQUE (deal_date, ticker, client_name, transaction_type, quantity, trade_price)
        )
    """)


def parse_block(records, deal_type, today):
    rows = []
    for d in records or []:
        try:
            qty = d.get("quantityTraded") or d.get("qty") or "0"
            rows.append((
                today,
                (d.get("symbol") or "").strip(),
                (d.get("clientName") or "").strip(),
                deal_type,
                (d.get("buySell") or d.get("buyVsSell") or "").strip().upper(),
                int(str(qty).replace(",", "") or 0),
                float(str(d.get("tradePrice") or d.get("watp") or 0).replace(",", "")),
            ))
        except Exception:
            continue
    return [r for r in rows if r[1]]   # keep rows with a ticker


def main():
    today = datetime.today().strftime("%Y-%m-%d")
    sess = requests.Session()
    sess.headers.update(HEADERS)
    # Prime cookies: homepage, then the large-deals page (sets the tokens the API needs),
    # with a short settle pause. NSE serves an HTML challenge if you hit the API too soon.
    sess.get("https://www.nseindia.com", timeout=20)
    time.sleep(1.5)
    sess.get("https://www.nseindia.com/market-data/large-deals", timeout=20)
    time.sleep(1.0)

    resp = sess.get(SNAPSHOT, timeout=20)
    if resp.status_code != 200:
        sys.exit(f"NSE returned {resp.status_code}")
    data = None
    for attempt in range(3):
        body = (resp.text or "").strip()
        ctype = resp.headers.get("content-type", "").lower()
        if body and "json" in ctype:
            try:
                data = resp.json(); break
            except Exception:
                pass
        # empty body or HTML challenge — re-prime briefly and retry
        time.sleep(2.5)
        sess.get("https://www.nseindia.com/market-data/large-deals", timeout=20)
        resp = sess.get(SNAPSHOT, timeout=20)

    if data is None:
        body = (resp.text or "").strip()
        if not body:
            print("NSE returned an EMPTY response (HTTP %s, %s)." % (resp.status_code, resp.headers.get("content-type","")))
            print("Almost always means: no live large-deals right now (after-hours / non-trading) "
                  "OR the session needs warming. Try again ~30 min after market open on a trading day.")
            return
        sys.exit("NSE returned non-JSON. First 200 chars:\n" + body[:200])

    # import json; print(json.dumps(data, indent=2)[:1500])   # <- uncomment to inspect keys
    rows = []
    rows += parse_block(data.get("BULK_DEALS_DATA"), "BULK", today)
    rows += parse_block(data.get("BLOCK_DEALS_DATA"), "BLOCK", today)

    if not rows:
        print("No deals parsed — check the JSON field names (uncomment the debug line).")
        return

    conn = psycopg2.connect(URL); conn.autocommit = True
    cur = conn.cursor()
    ensure_table(cur)
    execute_values(cur, """
        INSERT INTO institutional_large_deals
          (deal_date, ticker, client_name, deal_type, transaction_type, quantity, trade_price)
        VALUES %s
        ON CONFLICT (deal_date, ticker, client_name, transaction_type, quantity, trade_price)
        DO NOTHING
    """, rows)
    print(f"institutional_large_deals: upserted {len(rows)} bulk/block deal rows for {today}")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
