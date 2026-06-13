#!/usr/bin/env python3
"""
_scripts/fetch_shp.py
─────────────────────────────────────────────────────────────────────────────
Fetches quarterly shareholding pattern from NSE for all stocks.
Uses curl_cffi with Chrome120 TLS fingerprint to bypass NSE bot protection.

Usage:
  python _scripts/fetch_shp.py                        # all stocks from DB
  python _scripts/fetch_shp.py --symbol WABAG         # single stock
  python _scripts/fetch_shp.py --limit 50             # first 50 from DB
  python _scripts/fetch_shp.py --output data/shp/     # custom output dir

Install:
  pip install curl_cffi psycopg2-binary python-dotenv pandas

Env vars (.env.local):
  DATABASE_URL=postgresql://...  (or NEON_DATABASE_URL)
"""

import sys
import json
import os
import time
import argparse
import csv
from pathlib import Path
from datetime import datetime

try:
    from curl_cffi import requests as cffi_requests
except ImportError:
    print("ERROR: curl_cffi not installed. Run: pip install curl_cffi", file=sys.stderr)
    sys.exit(1)

try:
    from dotenv import load_dotenv
    env_path = Path(".env.local")
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()
except ImportError:
    pass

# ─── Config ───────────────────────────────────────────────────────────────────
NSE_BASE    = "https://www.nseindia.com"
DELAY_SEC   = 1.5   # polite delay between requests
OUTPUT_DIR  = Path("data") / "raw" / "shareholding_nse"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive",
    "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}

# ─── Session factory ──────────────────────────────────────────────────────────
def make_session():
    """Create a fresh Chrome120-fingerprinted session primed with NSE cookies."""
    session = cffi_requests.Session(impersonate="chrome120")
    try:
        # Prime cookies — NSE requires a homepage visit first
        resp = session.get(NSE_BASE, headers=HEADERS, timeout=12)
        print(f"  [session] NSE homepage → HTTP {resp.status_code}")
        time.sleep(1.0)
    except Exception as e:
        print(f"  [session] Warning: homepage prime failed ({e})", file=sys.stderr)
    return session

# ─── Fetch one symbol ─────────────────────────────────────────────────────────
def fetch_shp(session, symbol: str) -> dict | None:
    """Fetch shareholding pattern JSON for one symbol."""
    url = f"{NSE_BASE}/api/corporate-shareholding-pattern?symbol={symbol}&series=EQ"
    try:
        resp = session.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 401:
            print(f"  [{symbol}] 401 — session expired, will refresh", file=sys.stderr)
            return None
        else:
            print(f"  [{symbol}] HTTP {resp.status_code}", file=sys.stderr)
            return None
    except Exception as e:
        print(f"  [{symbol}] Error: {e}", file=sys.stderr)
        return None

# ─── Parse SHP response ───────────────────────────────────────────────────────
def parse_shp(symbol: str, data: dict) -> list[dict]:
    """
    Extract the most recent 8 quarters of promoter/FII/DII/retail data.
    Returns a list of flat dicts ready for DB insertion.
    """
    rows = []
    try:
        quarters = data.get("data", [])
        for q in quarters[-8:]:  # last 8 quarters
            date_str = q.get("date", "")
            shareholding = q.get("shareholding", [])

            row = {
                "symbol": symbol,
                "report_date": date_str,
                "promoter_pct": None,
                "fii_pct": None,
                "dii_pct": None,
                "retail_pct": None,
                "pledge_pct": None,
            }

            for item in shareholding:
                name = (item.get("name") or "").lower()
                pct  = item.get("percentageOfShareHolding") or item.get("percentOfShares")
                try:
                    pct = float(pct) if pct else None
                except (ValueError, TypeError):
                    pct = None

                if "promoter" in name:
                    row["promoter_pct"] = pct
                elif "foreign" in name or "fii" in name or "fpi" in name:
                    row["fii_pct"] = pct
                elif "domestic" in name or "dii" in name or "mutual" in name:
                    if row["dii_pct"] is None:
                        row["dii_pct"] = pct
                    else:
                        row["dii_pct"] = round((row["dii_pct"] or 0) + (pct or 0), 2)
                elif "public" in name or "retail" in name:
                    row["retail_pct"] = pct

            rows.append(row)
    except Exception as e:
        print(f"  [{symbol}] Parse error: {e}", file=sys.stderr)

    return rows

# ─── Save to JSON + CSV ───────────────────────────────────────────────────────
def save_output(symbol: str, raw: dict, parsed: list[dict], out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

    # Raw JSON for auditing
    raw_path = out_dir / f"{symbol}_raw.json"
    with open(raw_path, "w") as f:
        json.dump(raw, f, indent=2)

    # Parsed CSV for loader
    if parsed:
        csv_path = out_dir / f"{symbol}.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=parsed[0].keys())
            writer.writeheader()
            writer.writerows(parsed)

        print(f"  [{symbol}] ✓ {len(parsed)} quarters saved → {csv_path}")
    else:
        print(f"  [{symbol}] ⚠ No parseable data")

# ─── Load symbols from DB or CSV ──────────────────────────────────────────────
def get_symbols(only_symbol: str | None, limit: int) -> list[str]:
    if only_symbol:
        return [only_symbol.upper()]

    # Try DB first
    db_url = os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")
    if db_url:
        try:
            import psycopg2
            conn = psycopg2.connect(db_url)
            cur  = conn.cursor()
            cur.execute("SELECT symbol FROM company_master ORDER BY symbol")
            syms = [r[0] for r in cur.fetchall()]
            conn.close()
            return syms[:limit] if limit else syms
        except Exception as e:
            print(f"DB lookup failed ({e}), falling back to CSV", file=sys.stderr)

    # Fallback: watchlist CSV
    csv_path = Path("data") / "watchlist_symbols.csv"
    if csv_path.exists():
        with open(csv_path) as f:
            reader = csv.reader(f)
            next(reader, None)  # skip header
            syms = [row[0].strip().upper() for row in reader if row]
        return syms[:limit] if limit else syms

    raise RuntimeError("No DATABASE_URL and no data/watchlist_symbols.csv found")

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="NSE Shareholding Pattern Fetcher")
    parser.add_argument("--symbol",  help="Single stock symbol")
    parser.add_argument("--limit",   type=int, default=0, help="Max symbols to process")
    parser.add_argument("--output",  default=str(OUTPUT_DIR), help="Output directory")
    args = parser.parse_args()

    out_dir = Path(args.output)
    symbols = get_symbols(args.symbol, args.limit)

    print("━" * 52)
    print(" AACapital — NSE Shareholding Pattern Fetcher")
    print("━" * 52)
    print(f"  Symbols : {len(symbols)}")
    print(f"  Output  : {out_dir}")
    print()

    session = make_session()
    results = {"ok": 0, "fail": 0, "skip": 0}
    session_hits = 0

    for i, symbol in enumerate(symbols, 1):
        print(f"[{i:3d}/{len(symbols)}] {symbol}")

        # Refresh session every 30 requests (NSE sessions expire)
        if session_hits > 0 and session_hits % 30 == 0:
            print("  [session] Refreshing...")
            session = make_session()

        # Skip if already fetched today
        csv_path = out_dir / f"{symbol}.csv"
        if csv_path.exists():
            mtime = datetime.fromtimestamp(csv_path.stat().st_mtime)
            if (datetime.now() - mtime).days < 1:
                print(f"  [{symbol}] already fetched today, skipping")
                results["skip"] += 1
                continue

        data = fetch_shp(session, symbol)
        session_hits += 1

        if data is None:
            # Session expired — refresh and retry once
            session = make_session()
            session_hits = 0
            data = fetch_shp(session, symbol)

        if data:
            parsed = parse_shp(symbol, data)
            save_output(symbol, data, parsed, out_dir)
            results["ok"] += 1
        else:
            print(f"  [{symbol}] ✗ Failed")
            results["fail"] += 1

        time.sleep(DELAY_SEC)

    print()
    print("━" * 52)
    print(f"✅ Success : {results['ok']}")
    print(f"⏭  Skipped : {results['skip']}")
    print(f"❌ Failed  : {results['fail']}")
    print("━" * 52)
    print(f"\nNext: build load-shareholding.ts to push CSVs to Neon")

if __name__ == "__main__":
    main()
