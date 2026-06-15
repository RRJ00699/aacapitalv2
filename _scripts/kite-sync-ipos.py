"""
_scripts/kite-sync-ipos.py
Fetches live IPO data from Zerodha Kite + NSE and populates ipo_intelligence table.
Also captures listing day OI, VWAP, and delivery data for the prediction engine.

Usage:
  python _scripts/kite-sync-ipos.py                    # fetch current/upcoming IPOs
  python _scripts/kite-sync-ipos.py --listing           # capture listing day signals
  python _scripts/kite-sync-ipos.py --symbol SYMBOL     # fetch single IPO listing data
  python _scripts/kite-sync-ipos.py --backfill          # backfill historical from ipo_history

Requirements:
  pip install kiteconnect psycopg2-binary python-dotenv pandas requests
"""

import os
import sys
import time
import json
import argparse
import requests
import psycopg2
import psycopg2.extras
import pandas as pd
from datetime import date, datetime, timedelta
from dotenv import load_dotenv

load_dotenv(".env.local")
load_dotenv(".env")

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")
KITE_API_KEY = os.getenv("KITE_API_KEY")
KITE_ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN")

parser = argparse.ArgumentParser()
parser.add_argument("--listing",  action="store_true", help="Capture listing day signals")
parser.add_argument("--symbol",   help="Single symbol")
parser.add_argument("--backfill", action="store_true", help="Backfill from ipo_history")
args = parser.parse_args()

# ── Kite setup ────────────────────────────────────────────────────────────────
try:
    from kiteconnect import KiteConnect
    kite = KiteConnect(api_key=KITE_API_KEY)
    kite.set_access_token(KITE_ACCESS_TOKEN)
    KITE_AVAILABLE = True
except Exception as e:
    print(f"⚠ Kite not available: {e}")
    KITE_AVAILABLE = False

# ── DB ────────────────────────────────────────────────────────────────────────
def get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode="require",
                            cursor_factory=psycopg2.extras.RealDictCursor)

# ── Fetch current IPOs from NSE ────────────────────────────────────────────────
def fetch_nse_ipos():
    """Fetch upcoming and recently listed IPOs from NSE."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://www.nseindia.com",
    }
    session = requests.Session()
    session.headers.update(headers)

    ipos = []
    # NSE IPO endpoints
    urls = [
        "https://www.nseindia.com/api/ipo-current-allotment",
        "https://www.nseindia.com/api/ipo-detail",
    ]
    try:
        # Get cookies first
        session.get("https://www.nseindia.com", timeout=10)
        time.sleep(1)
        r = session.get("https://www.nseindia.com/api/ipo-current-allotment", timeout=10)
        if r.status_code == 200:
            data = r.json()
            ipos.extend(data if isinstance(data, list) else [])
    except Exception as e:
        print(f"  ⚠ NSE IPO fetch failed: {e}")

    return ipos

# ── Fetch listing day signals from Kite ───────────────────────────────────────
def fetch_listing_signals(symbol: str, listing_date: date, issue_price: float) -> dict:
    """
    Fetch intraday 15-min candles on listing day.
    Compute VWAP at open, 30min, 60min.
    """
    if not KITE_AVAILABLE:
        return {}

    try:
        # Get instrument token
        instruments = kite.instruments("NSE")
        token_map   = {i["tradingsymbol"]: i["instrument_token"] for i in instruments}
        token       = token_map.get(symbol) or token_map.get(f"{symbol}-EQ")
        if not token:
            print(f"  ✗ {symbol} — not found in Kite instruments")
            return {}

        # Fetch 15-min candles for listing day
        candles = kite.historical_data(
            instrument_token=token,
            from_date=listing_date,
            to_date=listing_date,
            interval="15minute",
        )

        if not candles:
            return {}

        df = pd.DataFrame(candles)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")

        # Compute cumulative VWAP
        df["typical_price"] = (df["high"] + df["low"] + df["close"]) / 3
        df["tp_vol"]        = df["typical_price"] * df["volume"]
        df["cum_tp_vol"]    = df["tp_vol"].cumsum()
        df["cum_vol"]       = df["volume"].cumsum()
        df["vwap"]          = df["cum_tp_vol"] / df["cum_vol"]

        # Snapshots
        opening_candle    = df.iloc[0]
        candle_30min      = df[df["date"].dt.time >= pd.Timestamp("10:00:00").time()].iloc[0] if len(df) > 1 else None
        candle_60min      = df[df["date"].dt.time >= pd.Timestamp("10:15:00").time()].iloc[0] if len(df) > 2 else None

        listing_open  = float(opening_candle["open"])
        vwap_open     = float(opening_candle["vwap"])
        vwap_30min    = float(candle_30min["vwap"]) if candle_30min is not None else vwap_open
        vwap_60min    = float(candle_60min["vwap"]) if candle_60min is not None else vwap_30min
        vwap_day      = float(df.iloc[-1]["vwap"])

        listing_close = float(df.iloc[-1]["close"])
        listing_high  = float(df["high"].max())
        listing_low   = float(df["low"].min())
        volume_total  = int(df["volume"].sum())
        volume_first  = int(df.iloc[:2]["volume"].sum()) if len(df) >= 2 else volume_total

        # Momentum chase check: at 10:00 AM, is price above open AND above VWAP?
        mc_price  = float(candle_30min["close"]) if candle_30min is not None else listing_open
        mc_entry  = mc_price > listing_open and mc_price > vwap_30min

        # Return calculation
        r_day1 = (listing_close - issue_price) / issue_price if issue_price else None

        # Get delivery %
        delivery_pct = None
        try:
            quote = kite.quote(f"NSE:{symbol}")
            delivery_pct = quote.get(f"NSE:{symbol}", {}).get("delivery_percentage")
        except:
            pass

        return {
            "listing_open":         listing_open,
            "listing_high":         listing_high,
            "listing_low":          listing_low,
            "listing_close":        listing_close,
            "vwap_open":            vwap_open,
            "vwap_30min":           vwap_30min,
            "vwap_60min":           vwap_60min,
            "vwap_day":             vwap_day,
            "open_above_vwap":      listing_open > vwap_open,
            "open_above_issue":     listing_open > issue_price if issue_price else None,
            "momentum_chase_entry": mc_entry,
            "volume_total":         volume_total,
            "volume_first_30min":   volume_first,
            "volume_ratio":         volume_first / volume_total if volume_total else None,
            "delivery_pct":         delivery_pct,
            "return_day1":          r_day1,
            "candles_15min":        json.dumps(candles, default=str),
        }
    except Exception as e:
        print(f"  ✗ {symbol} listing signals error: {e}")
        return {}

# ── Backfill from ipo_history ─────────────────────────────────────────────────
def backfill_from_history():
    """
    Transfer data from existing ipo_history table into ipo_intelligence.
    Maps columns from old schema to new enriched schema.
    """
    conn = get_conn()
    cur  = conn.cursor()

    # Check what columns ipo_history has
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'ipo_history' AND table_schema = 'public'
        ORDER BY ordinal_position
    """)
    cols = [r["column_name"] for r in cur.fetchall()]
    print(f"  ipo_history columns: {cols}")

    cur.execute("SELECT * FROM ipo_history ORDER BY listing_date NULLS LAST LIMIT 5")
    sample = cur.fetchall()
    if sample:
        print(f"\n  Sample row: {dict(sample[0])}")

    cur.execute("SELECT COUNT(*) as n FROM ipo_history")
    n = cur.fetchone()["n"]
    print(f"\n  Total IPOs in ipo_history: {n}")
    print("  Use this data to populate ipo_intelligence table.")
    print("  Column mapping needed — share ipo_history schema for full mapping.")

    conn.close()

# ── Save listing signals ───────────────────────────────────────────────────────
def save_listing_signals(symbol: str, listing_date: date, signals: dict):
    if not signals:
        return
    conn = get_conn()
    cur  = conn.cursor()
    cols = list(signals.keys())
    vals = list(signals.values())
    cur.execute(f"""
        INSERT INTO ipo_listing_signals
          (symbol, listing_date, {', '.join(cols)})
        VALUES (%s, %s, {', '.join(['%s']*len(cols))})
        ON CONFLICT (symbol, listing_date) DO UPDATE SET
          {', '.join([f'{c}=EXCLUDED.{c}' for c in cols])},
          created_at = NOW()
    """, [symbol, listing_date] + vals)
    conn.commit()
    cur.close()
    conn.close()
    print(f"  ✓ Saved listing signals for {symbol}")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("═" * 50)
    print("  AACapital — Kite IPO Sync")
    print("═" * 50)

    if args.backfill:
        print("\nBackfilling from ipo_history...")
        backfill_from_history()
        return

    if args.listing:
        # Fetch listing day signals for today's listing IPOs
        conn = get_conn()
        cur  = conn.cursor()
        today = date.today()
        cur.execute("""
            SELECT symbol, issue_price, listing_date
            FROM ipo_intelligence
            WHERE listing_date = %s AND symbol IS NOT NULL
        """, [today])
        listing_today = cur.fetchall()
        conn.close()

        if not listing_today:
            print(f"\n  No IPOs listing today ({today})")
            return

        print(f"\n  {len(listing_today)} IPO(s) listing today:")
        for ipo in listing_today:
            sym = ipo["symbol"]
            print(f"\n  [{sym}] Fetching listing day signals...")
            signals = fetch_listing_signals(sym, today, float(ipo["issue_price"] or 0))
            save_listing_signals(sym, today, signals)
            if signals:
                print(f"    Listing open: ₹{signals.get('listing_open')}")
                print(f"    VWAP open:    ₹{signals.get('vwap_open'):.2f}")
                print(f"    MC Entry?     {'✅ YES' if signals.get('momentum_chase_entry') else '❌ NO'}")
                print(f"    Day1 return:  {signals.get('return_day1',0)*100:.1f}%")
        return

    if args.symbol:
        # Single symbol listing data
        print(f"\nFetching listing signals for {args.symbol}...")
        conn = get_conn()
        cur  = conn.cursor()
        cur.execute("SELECT * FROM ipo_intelligence WHERE symbol ILIKE %s LIMIT 1", [args.symbol])
        ipo = cur.fetchone()
        conn.close()
        if ipo:
            signals = fetch_listing_signals(args.symbol, ipo["listing_date"], float(ipo["issue_price"] or 0))
            save_listing_signals(args.symbol, ipo["listing_date"], signals)
        else:
            print(f"  ✗ {args.symbol} not found in ipo_intelligence")
        return

    # Default: fetch current IPOs from NSE
    print("\nFetching current IPOs from NSE...")
    nse_ipos = fetch_nse_ipos()
    print(f"  Found {len(nse_ipos)} IPOs from NSE")
    for ipo in nse_ipos[:5]:
        print(f"  → {ipo}")

    print("\n✅ Done")
    print("\nNext steps:")
    print("  1. Populate ipo_intelligence table with historical data")
    print("  2. Run: python _scripts/engines/ipo_intelligence_engine.py --mode=backtest")
    print("  3. On listing days: python _scripts/kite-sync-ipos.py --listing")

if __name__ == "__main__":
    main()
