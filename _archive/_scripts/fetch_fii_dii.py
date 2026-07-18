#!/usr/bin/env python3
"""
_scripts/fetch_fii_dii.py
─────────────────────────────────────────────────────────────────────────────
Fetches daily FII/DII institutional flow data from NSE and inserts into
the daily_institutional_flows table in Neon PostgreSQL.

Runs daily via GitHub Actions at 6:30 PM IST (13:00 UTC) Mon–Fri.

Usage:
  python _scripts/fetch_fii_dii.py                # today's data
  python _scripts/fetch_fii_dii.py --dry-run      # print only, no DB insert
  python _scripts/fetch_fii_dii.py --days 30      # last 30 days of history

Install:
  pip install curl_cffi psycopg2-binary python-dotenv

Env vars (.env.local):
  DATABASE_URL=postgresql://...
"""

import sys
import json
import os
import time
import argparse
from datetime import datetime, timedelta
from pathlib import Path

try:
    from curl_cffi import requests as cffi_requests
except ImportError:
    print("ERROR: curl_cffi not installed. Run: pip install curl_cffi", file=sys.stderr)
    sys.exit(1)

try:
    from dotenv import load_dotenv
    env_path = Path(".env.local")
    load_dotenv(env_path if env_path.exists() else ".env")
except ImportError:
    pass

# ─── Config ───────────────────────────────────────────────────────────────────
NSE_BASE = "https://www.nseindia.com"
HEADERS  = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/reports/fii-dii",
    "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}

# ─── Session ──────────────────────────────────────────────────────────────────
def make_session():
    session = cffi_requests.Session(impersonate="chrome120")
    try:
        r = session.get(NSE_BASE, headers=HEADERS, timeout=12)
        print(f"[session] NSE prime → HTTP {r.status_code}")
        time.sleep(1.2)
    except Exception as e:
        print(f"[session] Prime warning: {e}", file=sys.stderr)
    return session

# ─── Fetch FII/DII from NSE ───────────────────────────────────────────────────
def fetch_fii_dii_today(session) -> list[dict]:
    """
    NSE endpoint returns last few trading days of FII/DII data.
    Returns list of dicts with keys matching our DB schema.
    """
    url = f"{NSE_BASE}/api/fiidiiTradeReact"
    try:
        resp = session.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"[fii-dii] HTTP {resp.status_code}", file=sys.stderr)
            return []

        raw = resp.json()
        return parse_fii_dii(raw)

    except Exception as e:
        print(f"[fii-dii] Fetch error: {e}", file=sys.stderr)
        return []


def parse_fii_dii(raw: list | dict) -> list[dict]:
    """
    NSE returns a list like:
    [
      {
        "date": "13-Jun-2026",
        "category": "FII/FPI *",
        "buyValue": "12345.67",
        "sellValue": "11234.56",
        "netValue": "1111.11"
      },
      ...
    ]
    We consolidate FII rows and DII rows into one record per date.
    """
    rows = raw if isinstance(raw, list) else raw.get("data", [])
    by_date: dict[str, dict] = {}

    for item in rows:
        date_str = item.get("date", "")
        try:
            # Parse "13-Jun-2026" → "2026-06-13"
            trade_date = datetime.strptime(date_str, "%d-%b-%Y").strftime("%Y-%m-%d")
        except ValueError:
            continue

        if trade_date not in by_date:
            by_date[trade_date] = {
                "trade_date": trade_date,
                "fii_buy_gross": 0.0, "fii_sell_gross": 0.0, "fii_net": 0.0,
                "dii_buy_gross": 0.0, "dii_sell_gross": 0.0, "dii_net": 0.0,
            }

        cat  = (item.get("category") or "").upper()
        buy  = float(item.get("buyValue")  or 0)
        sell = float(item.get("sellValue") or 0)
        net  = float(item.get("netValue")  or 0)

        if "FII" in cat or "FPI" in cat:
            by_date[trade_date]["fii_buy_gross"]  += buy
            by_date[trade_date]["fii_sell_gross"] += sell
            by_date[trade_date]["fii_net"]        += net
        elif "DII" in cat or "MF" in cat or "INSURANCE" in cat:
            by_date[trade_date]["dii_buy_gross"]  += buy
            by_date[trade_date]["dii_sell_gross"] += sell
            by_date[trade_date]["dii_net"]        += net

    return sorted(by_date.values(), key=lambda r: r["trade_date"])


# ─── DB insert ────────────────────────────────────────────────────────────────
def upsert_to_db(records: list[dict], dry_run: bool = False):
    if not records:
        print("[db] No records to insert")
        return

    if dry_run:
        print("[dry-run] Would insert:")
        for r in records:
            print(f"  {r['trade_date']} | FII net: {r['fii_net']:+.2f} | DII net: {r['dii_net']:+.2f}")
        return

    db_url = os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")
    if not db_url:
        print("[db] ERROR: No DATABASE_URL in environment", file=sys.stderr)
        sys.exit(1)

    try:
        import psycopg2
        conn = psycopg2.connect(db_url)
        cur  = conn.cursor()

        for r in records:
            cur.execute("""
                INSERT INTO daily_institutional_flows
                    (trade_date, fii_buy_gross, fii_sell_gross, fii_net,
                     dii_buy_gross, dii_sell_gross, dii_net)
                VALUES (%(trade_date)s,
                        %(fii_buy_gross)s, %(fii_sell_gross)s, %(fii_net)s,
                        %(dii_buy_gross)s, %(dii_sell_gross)s, %(dii_net)s)
                ON CONFLICT (trade_date) DO UPDATE SET
                    fii_buy_gross  = EXCLUDED.fii_buy_gross,
                    fii_sell_gross = EXCLUDED.fii_sell_gross,
                    fii_net        = EXCLUDED.fii_net,
                    dii_buy_gross  = EXCLUDED.dii_buy_gross,
                    dii_sell_gross = EXCLUDED.dii_sell_gross,
                    dii_net        = EXCLUDED.dii_net
            """, r)

        conn.commit()
        conn.close()
        print(f"[db] ✓ Upserted {len(records)} records")

    except Exception as e:
        print(f"[db] Insert error: {e}", file=sys.stderr)
        sys.exit(1)


# ─── Also update market_regimes AMFI + FII component ────────────────────────
def update_market_regime_fii(latest: dict, dry_run: bool):
    """
    After inserting FII/DII, update the regime record for today
    to include the FII signal (positive/negative).
    """
    if dry_run or not latest:
        return

    db_url = os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")
    if not db_url:
        return

    try:
        import psycopg2
        conn = psycopg2.connect(db_url)
        cur  = conn.cursor()
        # Update today's regime row if it exists
        cur.execute("""
            UPDATE market_regimes
            SET fii_net_cr = %s, updated_at = NOW()
            WHERE evaluation_date = %s
        """, (latest["fii_net"] / 100, latest["trade_date"]))  # lakhs → crores
        conn.commit()
        conn.close()
    except Exception:
        pass  # Column may not exist yet — non-fatal


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="NSE FII/DII Daily Flow Tracker")
    parser.add_argument("--dry-run", action="store_true", help="Print data, skip DB insert")
    parser.add_argument("--days",    type=int, default=5, help="How many recent trading days to capture")
    args = parser.parse_args()

    print("━" * 52)
    print(" AACapital — FII/DII Daily Flow Tracker")
    print("━" * 52)
    print(f"  Mode    : {'DRY RUN' if args.dry_run else 'LIVE INSERT'}")
    print(f"  Time    : {datetime.now().strftime('%Y-%m-%d %H:%M IST')}")
    print()

    session = make_session()
    records = fetch_fii_dii_today(session)

    if not records:
        print("❌ No data retrieved from NSE. Market may be closed or API changed.")
        sys.exit(0)

    # Keep only the N most recent trading days
    records = records[-args.days:]

    print(f"[parse] {len(records)} trading day(s) retrieved:")
    for r in records:
        fii_signal = "▲ buying" if r["fii_net"] > 0 else "▼ selling"
        dii_signal = "▲ buying" if r["dii_net"] > 0 else "▼ selling"
        print(f"  {r['trade_date']} | FII {fii_signal} ₹{abs(r['fii_net']):.0f}Cr | DII {dii_signal} ₹{abs(r['dii_net']):.0f}Cr")

    upsert_to_db(records, dry_run=args.dry_run)

    if records and not args.dry_run:
        update_market_regime_fii(records[-1], dry_run=False)

    print()
    print("✅ Done.")

if __name__ == "__main__":
    main()
