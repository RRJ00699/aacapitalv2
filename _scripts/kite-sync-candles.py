"""
_scripts/kite-sync-candles.py
Syncs daily + weekly candles from Zerodha Kite Connect API into Neon DB.
Also fetches delivery percentage data.

Usage:
    python _scripts/kite-sync-candles.py              # sync last 5 days
    python _scripts/kite-sync-candles.py --backfill   # fetch 3 years history
    python _scripts/kite-sync-candles.py --symbol WABAG
    python _scripts/kite-sync-candles.py --days 1     # just today

.env.local:
    KITE_API_KEY=br9m41pn8nvvywnl
    KITE_API_SECRET=your_secret
    KITE_ACCESS_TOKEN=generated_daily_via_kite-auth.py

Requirements:
    pip install kiteconnect psycopg2-binary python-dotenv pandas
"""

import os
import sys
import time
import argparse
import psycopg2
import psycopg2.extras
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv(".env.local")
load_dotenv(".env")

API_KEY      = os.getenv("KITE_API_KEY", "br9m41pn8nvvywnl")
DATABASE_URL = os.getenv("CANDLES_DATABASE_URL") or os.getenv("LOCAL_DATABASE_URL")
NEON_URL     = os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")

parser = argparse.ArgumentParser()
parser.add_argument("--symbol",   help="Single symbol to sync")
parser.add_argument("--backfill", action="store_true", help="Fetch full 3-year history")
parser.add_argument("--days",     type=int, default=5, help="Days to sync (default 5)")
parser.add_argument("--target",   choices=["local","neon"], default=None,
                    help="Write target: local (default on Windows) or neon (for GitHub Actions)")
args = parser.parse_args()

# ── Write target: neon when --target neon OR when local DB is not configured ───
# GitHub Actions: CANDLES_DATABASE_URL not set → DATABASE_URL is None → auto-routes to Neon
# Windows local:  CANDLES_DATABASE_URL is set  → writes to local Postgres
_force_neon = (args.target == "neon")
WRITE_URL   = NEON_URL if (_force_neon or not DATABASE_URL) else DATABASE_URL
if not WRITE_URL:
    print("❌ No write target — set DATABASE_URL (Neon) or CANDLES_DATABASE_URL (local)")
    sys.exit(1)
_write_target = "Neon" if WRITE_URL == NEON_URL else "local Postgres"
print(f"  Write target: {_write_target}")

# ── Get Kite access token — from Neon DB first, env var fallback ───────────────
def get_access_token() -> str:
    # Try Neon DB first (auto-refreshed by kite-token-refresh.yml at 8AM)
    if NEON_URL:
        try:
            import psycopg2
            conn = psycopg2.connect(NEON_URL)
            cur  = conn.cursor()
            cur.execute("SELECT value FROM platform_config WHERE key='kite_access_token'")
            row = cur.fetchone()
            conn.close()
            if row and row[0] and row[0] != "not_set_yet":
                print(f"  Token from Neon DB ✓")
                return row[0]
        except Exception as e:
            print(f"  Neon token fetch failed: {e}")
    # Fall back to env var
    token = os.getenv("KITE_ACCESS_TOKEN", "")
    if token:
        print(f"  Token from env var ✓")
        return token
    print("❌ No Kite access token found.")
    print("   Run: python _scripts/refresh_kite_token.py")
    sys.exit(1)

ACCESS_TOKEN = get_access_token()

# ── Validate ──────────────────────────────────────────────────────────────────
if not API_KEY:
    print("❌ KITE_API_KEY not set in .env.local")
    sys.exit(1)

try:
    from kiteconnect import KiteConnect
except ImportError:
    print("❌ Run: pip install kiteconnect")
    sys.exit(1)

kite = KiteConnect(api_key=API_KEY)
kite.set_access_token(ACCESS_TOKEN)

# ── Instrument lookup ─────────────────────────────────────────────────────────
print("Loading Kite instruments...")
try:
    instruments = kite.instruments("NSE")
except Exception as e:
    print(f"❌ Failed to load instruments: {e}")
    print("   Your access token may have expired. Run: python _scripts/kite-auth.py")
    sys.exit(1)

symbol_to_token = {
    i["tradingsymbol"]: i["instrument_token"]
    for i in instruments if i["segment"] == "NSE"
}
print(f"  {len(symbol_to_token)} NSE instruments loaded\n")

# ── DB helpers ────────────────────────────────────────────────────────────────

def get_connection():
    """Write connection — local Postgres on Windows, Neon in GitHub Actions."""
    from urllib.parse import urlparse, unquote
    p  = urlparse(WRITE_URL)
    qs = dict(pair.split("=", 1) for pair in (p.query or "").split("&") if "=" in pair)
    kw = dict(host=p.hostname, port=p.port or 5432,
              dbname=p.path.lstrip("/"),
              user=unquote(p.username or ""),
              password=unquote(p.password or ""))
    if "sslmode" in qs: kw["sslmode"] = qs["sslmode"]
    return psycopg2.connect(**kw)

def get_symbols():
    if args.symbol:
        return [args.symbol.upper()]
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("SELECT symbol FROM company_master WHERE symbol IS NOT NULL ORDER BY symbol")
    symbols = [r[0] for r in cur.fetchall()]
    cur.close()
    conn.close()
    return symbols

def upsert_daily(symbol: str, candles: list) -> int:
    if not candles:
        return 0
    conn = get_connection()
    try:
        cur = conn.cursor()
        rows = [
            (symbol, c["date"].date(), c["open"], c["high"], c["low"], c["close"], c["volume"])
            for c in candles
        ]
        psycopg2.extras.execute_values(cur, """
            INSERT INTO price_candles (symbol, date, open, high, low, close, volume)
            VALUES %s
            ON CONFLICT (symbol, date) DO UPDATE SET
              open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
              close=EXCLUDED.close, volume=EXCLUDED.volume
        """, rows)
        conn.commit()
        cur.close()
        return len(rows)
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def upsert_weekly(symbol: str, weekly_rows: list) -> int:
    if not weekly_rows:
        return 0
    conn = get_connection()
    try:
        cur = conn.cursor()
        psycopg2.extras.execute_values(cur, """
            INSERT INTO price_candles_weekly (symbol, week_start, open, high, low, close, volume)
            VALUES %s
            ON CONFLICT (symbol, week_start) DO UPDATE SET
              open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
              close=EXCLUDED.close, volume=EXCLUDED.volume
        """, weekly_rows)
        conn.commit()
        cur.close()
        return len(weekly_rows)
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def upsert_delivery(symbol: str, dt: date, delivery_pct: float):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO technical_signals (symbol, date, delivery_pct)
            VALUES (%s,%s,%s)
            ON CONFLICT (symbol, date) DO UPDATE SET
              delivery_pct=EXCLUDED.delivery_pct
        """, (symbol, dt, delivery_pct))
        conn.commit()
        cur.close()
    except Exception:
        conn.rollback()  # non-critical, ignore
    finally:
        conn.close()

# ── Sync one symbol ───────────────────────────────────────────────────────────

def sync_symbol(symbol: str):
    token = symbol_to_token.get(symbol) or symbol_to_token.get(f"{symbol}-EQ")
    if not token:
        print(f"  ✗ {symbol} — not found in Kite NSE instruments")
        return

    end_date   = date.today()
    start_date = (end_date - timedelta(days=365*3)) if args.backfill else (end_date - timedelta(days=args.days + 5))

    # ── Daily candles ──
    try:
        candles = kite.historical_data(
            instrument_token=token,
            from_date=start_date,
            to_date=end_date,
            interval="day",
        )
        n = upsert_daily(symbol, candles)
        print(f"  ✓ daily  {symbol} — {n} rows")
    except Exception as e:
        print(f"  ✗ daily  {symbol} — {e}")
        return

    # ── Weekly (resample from daily) ──
    try:
        import pandas as pd
        df = pd.DataFrame(candles)
        if df.empty:
            return
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        weekly = df.resample("W-MON", closed="left", label="left").agg({
            "open": "first", "high": "max", "low": "min",
            "close": "last", "volume": "sum",
        }).dropna()
        rows = [
            (symbol, idx.date(), float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]), int(row["volume"]))
            for idx, row in weekly.iterrows()
        ]
        n = upsert_weekly(symbol, rows)
        print(f"  ✓ weekly {symbol} — {n} rows")
    except Exception as e:
        print(f"  ✗ weekly {symbol} — {e}")

    # ── Delivery % (today only) ──
    if not args.backfill:
        try:
            quote = kite.quote(f"NSE:{symbol}")
            pct   = quote.get(f"NSE:{symbol}", {}).get("delivery_percentage")
            if pct is not None:
                upsert_delivery(symbol, end_date, pct)
                print(f"  ✓ deliv  {symbol} — {pct:.1f}%")
        except Exception:
            pass  # non-critical

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    mode = "BACKFILL 3yr" if args.backfill else f"INCREMENTAL {args.days}d"
    print("═══════════════════════════════════════════")
    print(f"  AACapital — Kite Candle Sync ({mode})")
    print("═══════════════════════════════════════════\n")

    symbols = get_symbols()
    print(f"Stocks: {len(symbols)}\n")

    ok = fail = 0
    for i, symbol in enumerate(symbols, 1):
        print(f"[{i:3}/{len(symbols)}] {symbol}")
        try:
            sync_symbol(symbol)
            ok += 1
        except Exception as e:
            print(f"  ✗ {symbol} — fatal: {e}")
            fail += 1
        time.sleep(0.35)  # Kite rate limit ~3 req/sec

    print(f"\n✅ Done — {ok} ok, {fail} failed")

if __name__ == "__main__":
    main()
