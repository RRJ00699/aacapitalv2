#!/usr/bin/env python3
"""market_breadth.py — NIFTY advances/declines (U16, owner ask 2026-07-22).

Source: NSE /api/allIndices (same proven session pattern as
nse_preopen_capture / nse_anchor_backfill: curl_cffi chrome124 + priming).
The NIFTY 50 row carries advances/declines/unchanged. Stored as
platform_config key 'india_breadth' = {"adv":N,"dec":N,"unch":N,"asof":ts};
/api/market/global attaches it and the sidebar renders it.

Run:  venv/bin/python _scripts/market_breadth.py --apply   (dry-run default)
Cron (suggested, IST server):  */30 9-15 * * 1-5  <env> market_breadth.py --apply
FIRST RUN VERIFIES the payload shape — structure-tested only until then.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime

NSE = "https://www.nseindia.com"
HEADERS = {
    "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "accept": "application/json, text/plain, */*",
    "referer": NSE + "/market-data/live-market-indices",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    from curl_cffi import requests as cffi
    import psycopg2
    s = cffi.Session(impersonate="chrome124")
    s.get(NSE, headers=HEADERS, timeout=12); time.sleep(0.8)
    r = s.get(NSE + "/api/allIndices", headers=HEADERS, timeout=15)
    data = r.json()
    row = next((d for d in (data.get("data") or [])
                if str(d.get("index", "")).upper() == "NIFTY 50"), None)
    if not row:
        print("! NIFTY 50 row not found in allIndices — paste one payload sample")
        return 1
    breadth = {"adv": row.get("advances"), "dec": row.get("declines"),
               "unch": row.get("unchanged"),
               "asof": datetime.now().strftime("%Y-%m-%d %H:%M IST")}
    print(f"  breadth: {breadth}")
    if not a.apply:
        print("dry-run — rerun with --apply to store")
        return 0
    conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=20)
    cur = conn.cursor()
    cur.execute("""INSERT INTO platform_config (key, value) VALUES ('india_breadth', %s)
                   ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
                (json.dumps(breadth),))
    conn.commit(); conn.close()
    print("stored -> platform_config['india_breadth']")
    return 0


if __name__ == "__main__":
    sys.exit(main())
