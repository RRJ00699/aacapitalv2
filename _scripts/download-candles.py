"""
_scripts/download-candles.py
Downloads daily + weekly price candle CSVs from Yahoo Finance for all
stocks in company_master, saving to data/candles/daily/ and data/candles/weekly/

Yahoo Finance uses NSE suffix: WABAG -> WABAG.NS  (BSE: WABAG.BO)

Usage:
    python _scripts/download-candles.py
    python _scripts/download-candles.py --symbol WABAG
    python _scripts/download-candles.py --limit 10
    python _scripts/download-candles.py --type daily
    python _scripts/download-candles.py --resume

Requirements:
    pip install yfinance psycopg2-binary python-dotenv pandas
"""

import os
import sys
import time
import argparse
import psycopg2
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

# ── Load env ──────────────────────────────────────────────────────────────────
load_dotenv(".env.local")
load_dotenv(".env")

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")

# ── Config ────────────────────────────────────────────────────────────────────
OUTPUT_DAILY  = Path("data/candles/daily")
OUTPUT_WEEKLY = Path("data/candles/weekly")

HISTORY_YEARS = 10        # how many years back to fetch
DELAY_BETWEEN = 0.5       # seconds between requests
SUFFIX_PRIMARY   = ".NS"  # NSE
SUFFIX_FALLBACK  = ".BO"  # BSE fallback

# ── Arg parse ─────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--symbol", help="Download single symbol only")
parser.add_argument("--limit",  type=int, help="Max number of stocks to process")
parser.add_argument("--type",   choices=["daily", "weekly", "both"], default="both")
parser.add_argument("--resume", action="store_true", help="Skip already-downloaded files")
args = parser.parse_args()

# ── Setup ─────────────────────────────────────────────────────────────────────
OUTPUT_DAILY.mkdir(parents=True, exist_ok=True)
OUTPUT_WEEKLY.mkdir(parents=True, exist_ok=True)

try:
    import yfinance as yf
except ImportError:
    print("❌ yfinance not installed. Run: pip install yfinance pandas")
    sys.exit(1)

# ── DB ────────────────────────────────────────────────────────────────────────
def get_symbols():
    if args.symbol:
        return [args.symbol.upper()]
    if not DATABASE_URL:
        print("❌ DATABASE_URL not set in .env.local")
        sys.exit(1)
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cur  = conn.cursor()
        cur.execute("""
            SELECT symbol FROM company_master
            WHERE symbol IS NOT NULL AND symbol != ''
            ORDER BY symbol
        """)
        symbols = [r[0] for r in cur.fetchall()]
        cur.close()
        conn.close()
        return symbols
    except Exception as e:
        print(f"❌ DB error: {e}")
        sys.exit(1)

# ── Download ──────────────────────────────────────────────────────────────────
def download_symbol(symbol: str) -> dict:
    """
    Returns { daily: bool, weekly: bool }
    """
    result = {"daily": False, "weekly": False}

    daily_file  = OUTPUT_DAILY  / f"{symbol}.csv"
    weekly_file = OUTPUT_WEEKLY / f"{symbol}.csv"

    need_daily  = args.type in ("daily",  "both") and not (args.resume and daily_file.exists()  and daily_file.stat().st_size  > 500)
    need_weekly = args.type in ("weekly", "both") and not (args.resume and weekly_file.exists() and weekly_file.stat().st_size > 500)

    if not need_daily and not need_weekly:
        print(f"  ○ {symbol} — skipped (already exists)")
        return {"daily": True, "weekly": True}

    # Try NSE first, then BSE
    ticker_obj = None
    used_suffix = ""
    for suffix in [SUFFIX_PRIMARY, SUFFIX_FALLBACK]:
        ticker = f"{symbol}{suffix}"
        t = yf.Ticker(ticker)
        # Quick probe: fetch 5 days
        probe = t.history(period="5d", auto_adjust=True)
        if not probe.empty:
            ticker_obj  = t
            used_suffix = suffix
            break

    if ticker_obj is None:
        print(f"  ✗ {symbol} — not found on NSE or BSE")
        return result

    # ── Daily ──
    if need_daily:
        try:
            df = ticker_obj.history(period=f"{HISTORY_YEARS}y", interval="1d", auto_adjust=True)
            if df.empty:
                print(f"  ✗ daily   {symbol}{used_suffix} — no data")
            else:
                df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
                df.index = df.index.tz_localize(None)  # remove tz for clean CSV
                df.index.name = "Date"
                df.to_csv(daily_file)
                print(f"  ✓ daily   {symbol}{used_suffix} — {len(df)} rows → {daily_file.name}")
                result["daily"] = True
        except Exception as e:
            print(f"  ✗ daily   {symbol} — {e}")

    # ── Weekly ──
    if need_weekly:
        try:
            df = ticker_obj.history(period=f"{HISTORY_YEARS}y", interval="1wk", auto_adjust=True)
            if df.empty:
                print(f"  ✗ weekly  {symbol}{used_suffix} — no data")
            else:
                df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
                df.index = df.index.tz_localize(None)
                df.index.name = "Date"
                df.to_csv(weekly_file)
                print(f"  ✓ weekly  {symbol}{used_suffix} — {len(df)} rows → {weekly_file.name}")
                result["weekly"] = True
        except Exception as e:
            print(f"  ✗ weekly  {symbol} — {e}")

    return result

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("═══════════════════════════════════════════")
    print("  AACapital — Candle Downloader (yfinance)")
    print("═══════════════════════════════════════════")
    print(f"  Source : Yahoo Finance (NSE/BSE)")
    print(f"  Type   : {args.type}")
    print(f"  Resume : {args.resume}")
    print(f"  History: {HISTORY_YEARS} years")
    print()

    symbols = get_symbols()
    if args.limit:
        symbols = symbols[:args.limit]

    total = len(symbols)
    print(f"Stocks to process: {total}\n")

    ok_daily = ok_weekly = fail_daily = fail_weekly = 0
    failed = []

    for i, symbol in enumerate(symbols, 1):
        print(f"[{i:3}/{total}] {symbol}")
        r = download_symbol(symbol)

        if args.type in ("daily",  "both"):
            if r["daily"]:  ok_daily  += 1
            else:           fail_daily += 1; failed.append(f"{symbol}:daily")

        if args.type in ("weekly", "both"):
            if r["weekly"]: ok_weekly  += 1
            else:           fail_weekly += 1; failed.append(f"{symbol}:weekly")

        time.sleep(DELAY_BETWEEN)

    print()
    print("═══════════════════════════════════════════")
    print("  Summary")
    print("═══════════════════════════════════════════")
    if args.type in ("daily",  "both"): print(f"  Daily  : {ok_daily} ok, {fail_daily} failed")
    if args.type in ("weekly", "both"): print(f"  Weekly : {ok_weekly} ok, {fail_weekly} failed")

    if failed:
        print(f"\n  Failed symbols:")
        for s in failed: print(f"    {s}")

    print()
    if not failed:
        print("✅ All downloads complete!\n")
        print("Next steps:")
        print("  npx tsx _scripts/loaders/load-daily-candles.ts --dry-run")
        print("  npx tsx _scripts/loaders/load-weekly-candles.ts --dry-run")
        print("  npx tsx _scripts/loaders/load-daily-candles.ts")
        print("  npx tsx _scripts/loaders/load-weekly-candles.ts")
        print("  python _scripts/engines/market_regime.py --backfill")
    else:
        print(f"⚠ Re-run with --resume to retry only the failed ones")

if __name__ == "__main__":
    main()
