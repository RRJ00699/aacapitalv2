#!/usr/bin/env python3
"""nse_anchor_backfill.py — anchor data from NSE issue-information (2026-07-23).

WHY: rule-validation showed the anchors "edge" may be a coverage artifact —
anchor_count is 58.7% and IPOMatrix only reaches back to 2021. NSE's own
issue-information page (owner-evidenced URL:
  https://www.nseindia.com/market-data/issue-information?symbol=X&series=EQ&type=Past)
carries the Issue Size text WITH the anchor portion ("Including Anchor
investor portion of N Equity Shares") and the Anchor Allocation Report link.

HOW: reuses the PROVEN session pattern from nse_preopen_capture.py (curl_cffi
chrome124 impersonation, homepage+page priming, timeout discipline). The
backing API for that page is /api/ipo-detail?symbol=..&series=EQ. Raw JSON
lands in DURABLE nse_issue_info (fill-empty; never re-fetch a stored symbol
unless --refetch); parse extracts anchor_portion_shares + report URL +
issue-price-derived anchor value; consolidate mines it into ipo_golden next.

Run (VM):  venv/bin/python _scripts/nse_anchor_backfill.py --limit 20 --apply
Dry-run default. Gentle: 2.5s between symbols, stops on 3 straight failures.
"""
import argparse
import json
import os
import re
import sys
import time

NSE_BASE = "https://www.nseindia.com"
PAGE = NSE_BASE + "/market-data/issue-information?symbol={sym}&series=EQ&type=Past"
API = NSE_BASE + "/api/ipo-detail?symbol={sym}&series=EQ"
HEADERS = {
    "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9",
    "referer": NSE_BASE + "/market-data/all-upcoming-issues-ipo",
}
ANCHOR_RX = re.compile(r"Anchor\s+investor\s+portion\s+of\s+([\d,]+)\s+Equity", re.I)


def prime(cffi):
    s = cffi.Session(impersonate="chrome124")
    s.get(NSE_BASE, headers=HEADERS, timeout=12); time.sleep(0.8)
    s.get(NSE_BASE + "/market-data/all-upcoming-issues-ipo", headers=HEADERS, timeout=12)
    time.sleep(0.8)
    return s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--symbol", help="single symbol (evidence run)")
    a = ap.parse_args()
    import psycopg2
    from curl_cffi import requests as cffi
    conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=25)
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute("SET statement_timeout = '60s'")
    if a.symbol:
        targets = [a.symbol.upper()]
    else:
        # golden rows missing anchor evidence, newest listings first
        cur.execute("""SELECT g.nse_symbol FROM ipo_golden g
            LEFT JOIN nse_issue_info n ON n.symbol = g.nse_symbol
            WHERE g.nse_symbol IS NOT NULL AND n.symbol IS NULL
              AND g.anchor_amount_cr IS NULL
            ORDER BY g.golden_filled_at DESC NULLS LAST LIMIT %s""", (a.limit,))
        targets = [r[0] for r in cur.fetchall()]
    if not targets:
        print("nothing to fetch — coverage complete for current targets")
        return 0
    s = prime(cffi)
    ok = fails = 0
    for sym in targets:
        try:
            r = s.get(API.format(sym=sym), headers=HEADERS, timeout=15)
            payload = r.json()
            raw = json.dumps(payload)[:200_000]
            issue_txt = json.dumps(payload)  # anchor line may sit at any depth
            m = ANCHOR_RX.search(issue_txt)
            shares = int(m.group(1).replace(",", "")) if m else None
            cur.execute("""INSERT INTO nse_issue_info (symbol, raw_json, anchor_portion_shares, fetched_at)
                VALUES (%s, %s::jsonb, %s, NOW())
                ON CONFLICT (symbol) DO UPDATE SET raw_json = EXCLUDED.raw_json,
                  anchor_portion_shares = COALESCE(nse_issue_info.anchor_portion_shares, EXCLUDED.anchor_portion_shares),
                  fetched_at = NOW()""", (sym, raw, shares))
            print(f"  {sym:14} anchor_shares={shares if shares else '—'}  bytes={len(raw)}")
            ok += 1; fails = 0
        except Exception as e:  # timeouts/blocks: the preopen script's discipline
            fails += 1
            print(f"  ! {sym}: {type(e).__name__}: {str(e)[:120]}")
            if fails >= 3:
                print("  3 straight failures — NSE throttling; stop, resume later")
                break
        time.sleep(2.5)
    if a.apply:
        conn.commit(); print(f"COMMITTED ({ok} symbols)")
    else:
        conn.rollback(); print(f"dry-run rolled back ({ok} fetched) — rerun with --apply")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
