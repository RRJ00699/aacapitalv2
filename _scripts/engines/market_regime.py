#!/usr/bin/env python3
"""
_scripts/engines/market_regime.py
─────────────────────────────────────────────────────────────────────────────
Market Regime Engine — V10 AACapital

Computes the daily market regime using:
  1. Nifty 50 vs its 200-day EMA  (trend filter)
  2. % of 200 watchlist stocks above their own 200-day EMA  (breadth filter)

Regime matrix:
  NORMAL   → Nifty > EMA200 AND breadth > 60%  → Deploy 70–100%
  VOLATILE → Nifty > EMA200 AND breadth 40–60% → Deploy 30–50%
  CAUTION  → Nifty > EMA200 AND breadth < 40%  → Deploy 20–30%
  BEARISH  → Nifty < EMA200                    → Deploy 0–20%

Usage:
  python _scripts/engines/market_regime.py               # compute + insert today
  python _scripts/engines/market_regime.py --dry-run     # print only
  python _scripts/engines/market_regime.py --backfill    # compute last 252 days

Install:
  pip install pandas numpy psycopg2-binary python-dotenv yfinance

Env vars (.env.local):
  DATABASE_URL=postgresql://...
"""

import sys
import os
import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

try:
    import pandas as pd
    import numpy as np
except ImportError:
    print("ERROR: pip install pandas numpy", file=sys.stderr)
    sys.exit(1)

try:
    import yfinance as yf
except ImportError:
    print("ERROR: pip install yfinance", file=sys.stderr)
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv(".env.local" if Path(".env.local").exists() else ".env")
except ImportError:
    pass


# ─── Regime matrix ────────────────────────────────────────────────────────────
def classify_regime(nifty_close: float, nifty_ema200: float, breadth_pct: float) -> dict:
    above_ema = nifty_close > nifty_ema200

    if not above_ema:
        return {
            "regime": "BEARISH",
            "label":  "Bearish — capital preservation",
            "deploy_min": 0,
            "deploy_max": 20,
            "ui_color":   "red",
            "simple_msg": "Protect capital. Stay mostly in cash.",
        }

    if breadth_pct >= 60:
        return {
            "regime": "NORMAL",
            "label":  "Normal — aggressive accumulation",
            "deploy_min": 70,
            "deploy_max": 100,
            "ui_color":   "green",
            "simple_msg": "Good time to invest. Deploy capital.",
        }

    if breadth_pct >= 40:
        return {
            "regime": "VOLATILE",
            "label":  "Volatile — selective stock picking",
            "deploy_min": 30,
            "deploy_max": 50,
            "ui_color":   "amber",
            "simple_msg": "Be selective. Only high-conviction ideas.",
        }

    return {
        "regime": "CAUTION",
        "label":  "Caution — wait for breadth recovery",
        "deploy_min": 20,
        "deploy_max": 30,
        "ui_color":   "amber",
        "simple_msg": "Reduce exposure. Wait for market to stabilise.",
    }


# ─── EMA computation ──────────────────────────────────────────────────────────
def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


# ─── Download Nifty data ──────────────────────────────────────────────────────
def get_nifty(period: str = "2y") -> pd.DataFrame:
    print("[nifty] Downloading ^NSEI...")
    df = yf.download("^NSEI", period=period, interval="1d", progress=False, auto_adjust=True)
    if df.empty:
        # Fallback to BSE Sensex if Nifty unavailable
        print("[nifty] ^NSEI failed, trying ^BSESN...")
        df = yf.download("^BSESN", period=period, interval="1d", progress=False, auto_adjust=True)
    df = df[["Close"]].dropna()
    df.columns = ["close"]
    df.index = pd.to_datetime(df.index).normalize()
    df["ema200"] = ema(df["close"], 200)
    return df


# ─── Compute breadth from local candle files ──────────────────────────────────
def compute_breadth_from_files(candle_dir: Path, as_of_date: pd.Timestamp) -> float:
    """
    Read all daily candle CSVs, compute EMA200 for each stock,
    and count what % are above their EMA200 on `as_of_date`.
    """
    candle_dir = Path(candle_dir)
    if not candle_dir.exists():
        print(f"[breadth] Warning: {candle_dir} not found — using 50% default")
        return 50.0

    files = list(candle_dir.glob("*.csv"))
    if not files:
        return 50.0

    above = 0
    total = 0

    for f in files:
        try:
            df = pd.read_csv(f, index_col=0, parse_dates=True)
            # Handle both yfinance column names
            close_col = None
            for col in ["Close", "close", "Adj Close"]:
                if col in df.columns:
                    close_col = col
                    break
            if not close_col or len(df) < 200:
                continue

            df.index = pd.to_datetime(df.index).normalize()
            df = df.sort_index()

            # Get data up to as_of_date
            df = df[df.index <= as_of_date]
            if len(df) < 200:
                continue

            closes = df[close_col].dropna()
            ema200 = ema(closes, 200).iloc[-1]
            last_close = closes.iloc[-1]

            total += 1
            if last_close > ema200:
                above += 1

        except Exception:
            continue

    if total == 0:
        return 50.0

    pct = round((above / total) * 100, 2)
    print(f"[breadth] {above}/{total} stocks above EMA200 = {pct}%")
    return pct


# ─── Compute breadth from Neon DB ────────────────────────────────────────────
def compute_breadth_from_db(db_url: str, as_of_date: str) -> float:
    """
    Read price_candles from Neon, compute breadth.
    More accurate than file-based — uses DB for speed.
    """
    try:
        import psycopg2
        conn = psycopg2.connect(db_url)
        cur  = conn.cursor()

        # Get all symbols with sufficient history
        cur.execute("""
            WITH symbol_counts AS (
                SELECT symbol, COUNT(*) as cnt
                FROM price_candles
                WHERE date <= %s
                GROUP BY symbol
                HAVING COUNT(*) >= 200
            ),
            latest_prices AS (
                SELECT DISTINCT ON (p.symbol)
                    p.symbol, p.close
                FROM price_candles p
                JOIN symbol_counts s ON s.symbol = p.symbol
                WHERE p.date <= %s
                ORDER BY p.symbol, p.date DESC
            ),
            ema_calc AS (
                SELECT
                    symbol,
                    AVG(close) OVER (
                        PARTITION BY symbol
                        ORDER BY date
                        ROWS BETWEEN 199 PRECEDING AND CURRENT ROW
                    ) as ema200_approx,
                    close,
                    date
                FROM price_candles
                WHERE date <= %s
            ),
            latest_ema AS (
                SELECT DISTINCT ON (symbol)
                    symbol, close, ema200_approx
                FROM ema_calc
                WHERE ema200_approx IS NOT NULL
                ORDER BY symbol, date DESC
            )
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN close > ema200_approx THEN 1 ELSE 0 END) as above
            FROM latest_ema
        """, (as_of_date, as_of_date, as_of_date))

        row = cur.fetchone()
        conn.close()

        if row and row[0] > 0:
            total, above = row[0], row[1] or 0
            pct = round((above / total) * 100, 2)
            print(f"[breadth] DB: {above}/{total} stocks above EMA200 = {pct}%")
            return pct

    except Exception as e:
        print(f"[breadth] DB compute failed: {e}", file=sys.stderr)

    return 50.0


# ─── Insert to market_regimes ─────────────────────────────────────────────────
def upsert_regime(record: dict, dry_run: bool):
    if dry_run:
        print("\n[dry-run] Would insert:")
        print(json.dumps(record, indent=2, default=str))
        return

    db_url = os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")
    if not db_url:
        print("[db] ERROR: No DATABASE_URL set", file=sys.stderr)
        sys.exit(1)

    try:
        import psycopg2
        conn = psycopg2.connect(db_url)
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO market_regimes
                (evaluation_date, nifty_close, nifty_ema_200,
                 breadth_percentage, active_regime,
                 recommended_allocation_min, recommended_allocation_max)
            VALUES
                (%(evaluation_date)s, %(nifty_close)s, %(nifty_ema_200)s,
                 %(breadth_percentage)s, %(active_regime)s,
                 %(deploy_min)s, %(deploy_max)s)
            ON CONFLICT (evaluation_date) DO UPDATE SET
                nifty_close              = EXCLUDED.nifty_close,
                nifty_ema_200            = EXCLUDED.nifty_ema_200,
                breadth_percentage       = EXCLUDED.breadth_percentage,
                active_regime            = EXCLUDED.active_regime,
                recommended_allocation_min = EXCLUDED.recommended_allocation_min,
                recommended_allocation_max = EXCLUDED.recommended_allocation_max
        """, record)
        conn.commit()
        conn.close()
        print(f"[db] ✓ Regime upserted for {record['evaluation_date']}")
    except Exception as e:
        print(f"[db] Insert error: {e}", file=sys.stderr)
        sys.exit(1)


# ─── Also update market_snapshot table if it exists ──────────────────────────
def update_snapshot(regime: str, nifty_close: float, dry_run: bool):
    if dry_run:
        return
    db_url = os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")
    if not db_url:
        return
    try:
        import psycopg2
        conn = psycopg2.connect(db_url)
        cur  = conn.cursor()
        cur.execute("""
            UPDATE market_snapshot
            SET market_regime = %s, nifty_price = %s, last_updated = NOW()
            WHERE id = 1
        """, (regime, nifty_close))
        if cur.rowcount == 0:
            cur.execute("""
                INSERT INTO market_snapshot (id, market_regime, nifty_price, last_updated)
                VALUES (1, %s, %s, NOW())
                ON CONFLICT (id) DO UPDATE SET
                    market_regime = EXCLUDED.market_regime,
                    nifty_price   = EXCLUDED.nifty_price,
                    last_updated  = NOW()
            """, (regime, nifty_close))
        conn.commit()
        conn.close()
    except Exception:
        pass  # Non-fatal — snapshot table may not exist yet


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="AACapital Market Regime Engine")
    parser.add_argument("--dry-run",  action="store_true", help="Print regime, skip DB")
    parser.add_argument("--backfill", action="store_true", help="Compute last 252 trading days")
    parser.add_argument("--candle-dir", default="data/candles/daily", help="Path to daily candle CSVs")
    args = parser.parse_args()

    print("━" * 56)
    print(" AACapital — Market Regime Engine")
    print("━" * 56)

    # Download Nifty data
    nifty = get_nifty(period="3y")
    if nifty.empty:
        print("❌ Failed to download Nifty data", file=sys.stderr)
        sys.exit(1)

    db_url = os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL") or ""

    # Determine dates to process
    if args.backfill:
        # Last 252 trading days where EMA200 is valid
        dates = nifty.dropna(subset=["ema200"]).index[-252:]
    else:
        dates = nifty.dropna(subset=["ema200"]).index[-1:]

    print(f"  Processing {len(dates)} date(s)...\n")

    for date in dates:
        date_str = date.strftime("%Y-%m-%d")
        row = nifty.loc[date]
        nifty_close = round(float(row["close"]), 2)
        nifty_ema   = round(float(row["ema200"]), 2)

        # Compute breadth
        if db_url and not args.backfill:
            breadth = compute_breadth_from_db(db_url, date_str)
        else:
            breadth = compute_breadth_from_files(Path(args.candle_dir), date)

        regime_info = classify_regime(nifty_close, nifty_ema, breadth)

        print(f"  {date_str}")
        print(f"  Nifty:   {nifty_close:,.0f} (EMA200: {nifty_ema:,.0f}) → {'ABOVE' if nifty_close > nifty_ema else 'BELOW'}")
        print(f"  Breadth: {breadth:.1f}%")
        print(f"  Regime:  {regime_info['regime']} — {regime_info['label']}")
        print(f"  Deploy:  {regime_info['deploy_min']}%–{regime_info['deploy_max']}%")
        print()

        record = {
            "evaluation_date":  date_str,
            "nifty_close":      nifty_close,
            "nifty_ema_200":    nifty_ema,
            "breadth_percentage": breadth,
            "active_regime":    regime_info["regime"],
            "deploy_min":       regime_info["deploy_min"],
            "deploy_max":       regime_info["deploy_max"],
        }

        upsert_regime(record, dry_run=args.dry_run)

        if not args.backfill:
            update_snapshot(regime_info["regime"], nifty_close, dry_run=args.dry_run)

    print("━" * 56)
    print("✅ Market Regime Engine complete.")
    print()
    print("API endpoint: GET /api/market/snapshot → { regime, deploy_min, deploy_max }")
    print("Today screen uses this to show the regime card.")

if __name__ == "__main__":
    main()
