#!/usr/bin/env python3
"""
reconcile_missing_candles.py — fix the company_master <-> price_candles closed loop.

Backstory: populate_company_master.py seeds the universe FROM price_candles, and the
daily sync (kite-sync-candles.py) fetches candles FROM company_master. So any stock
never in the original candle seed (the multibagger CSVs, which were all small/mid-cap)
can never enter either list — which is why 34 of the largest NSE names (RELIANCE,
HDFCBANK, TCS, INFY, SBIN, ICICIBANK, ...) have zero candles and null returns.

This breaks the loop for the names that matter:
  1. Find stock_fundamentals symbols with market_cap >= CUTOFF and NO candles.
  2. Register them in company_master (so the daily sync fetches them from now on).
  3. One-time backfill their ~10yr daily history from Kite, chunked to the
     2000-day-per-request limit, upsert into price_candles.

After this, run:  python _scripts/compute_candle_returns.py
so the scorecard's Momentum sub-score populates for the giants.

Run:  python _scripts/reconcile_missing_candles.py                 # cutoff 5000 cr (~37 large/mid)
      python _scripts/reconcile_missing_candles.py --cutoff 1000   # also include small-caps
      python _scripts/reconcile_missing_candles.py --dry-run       # show what it would do
Env:  DATABASE_URL (Neon). Kite token read from platform_config (refreshed daily by
      kite-token-refresh.yml); KITE_API_KEY (defaults to the app key); KITE_ACCESS_TOKEN fallback.
"""
import os
import sys
import time
import argparse
import logging
from datetime import date, timedelta

import psycopg2
import psycopg2.extras

# Load .env.local / .env exactly like kite-sync-candles.py does, BEFORE reading
# KITE_API_KEY. Otherwise the key falls back to the repo's placeholder default,
# which won't match the access_token (minted with your real key) — Kite then
# returns "Incorrect api_key or access_token" on historical_data even though the
# public instruments() call succeeds.
try:
    from dotenv import load_dotenv
    load_dotenv(".env.local")
    load_dotenv(".env")
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger()

URL      = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
API_KEY  = os.environ.get("KITE_API_KEY", "br9m41pn8nvvywnl")
YEARS    = int(os.environ.get("BACKFILL_YEARS", "10"))
CHUNK_DAYS = 1900          # < Kite's 2000-day/request cap for daily candles
RATE_SLEEP = 0.35          # ~3 req/sec

if not URL:
    sys.exit("DATABASE_URL not set")


def get_access_token(conn) -> str:
    """Token from Neon platform_config (auto-refreshed daily); env var fallback."""
    try:
        cur = conn.cursor()
        cur.execute("SELECT value FROM platform_config WHERE key='kite_access_token'")
        row = cur.fetchone()
        cur.close()
        if row and row[0] and row[0] != "not_set_yet":
            log.info("Kite token from Neon platform_config")
            return row[0]
    except Exception as e:
        log.warning(f"platform_config token fetch failed: {e}")
    tok = os.environ.get("KITE_ACCESS_TOKEN", "")
    if tok:
        log.info("Kite token from KITE_ACCESS_TOKEN env")
        return tok
    sys.exit("No Kite access token. Run: python _scripts/refresh_kite_token.py")


def find_missing(conn, cutoff: float):
    """stock_fundamentals rows >= cutoff market cap with no candles in price_candles."""
    cur = conn.cursor()
    cur.execute("""
        SELECT sf.nse_symbol, sf.name, sf.industry, sf.industry_group, sf.market_cap
        FROM stock_fundamentals sf
        LEFT JOIN (SELECT DISTINCT symbol FROM price_candles) pc
               ON pc.symbol = sf.nse_symbol
        WHERE pc.symbol IS NULL
          AND sf.nse_symbol IS NOT NULL
          AND sf.market_cap >= %s
        ORDER BY sf.market_cap DESC
    """, (cutoff,))
    rows = cur.fetchall()
    cur.close()
    return rows


def register_in_company_master(conn, rows):
    """Add the missing names so the daily sync fetches them going forward."""
    cur = conn.cursor()
    payload = [
        (sym, sym, name, industry, industry_group)
        for (sym, name, industry, industry_group, _mcap) in rows
    ]
    psycopg2.extras.execute_values(cur, """
        INSERT INTO company_master
            (symbol, nse_symbol, company_name, sector, industry_group, is_active, updated_at)
        VALUES %s
        ON CONFLICT (symbol) DO UPDATE SET
            nse_symbol = EXCLUDED.nse_symbol,
            is_active  = TRUE,
            updated_at = NOW()
    """, payload, template="(%s,%s,%s,%s,%s,TRUE,NOW())")
    conn.commit()
    cur.close()
    log.info(f"Registered {len(payload)} symbols in company_master")


def upsert_daily(conn, symbol, candles) -> int:
    if not candles:
        return 0
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cutoff", type=float, default=5000, help="Min market cap (cr) to backfill (default 5000)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(URL)
    missing = find_missing(conn, args.cutoff)
    log.info(f"{len(missing)} symbols >= {args.cutoff:.0f} cr have no candles:")
    for sym, name, _i, _ig, mcap in missing:
        log.info(f"   {sym:14} {str(name)[:28]:28} {float(mcap or 0):,.0f} cr")

    if args.dry_run:
        log.info("Dry run — no writes. Re-run without --dry-run to register + backfill.")
        conn.close()
        return
    if not missing:
        log.info("Nothing to do.")
        conn.close()
        return

    register_in_company_master(conn, missing)

    # ── Kite ──
    token = get_access_token(conn)
    try:
        from kiteconnect import KiteConnect
    except ImportError:
        sys.exit("pip install kiteconnect")
    kite = KiteConnect(api_key=API_KEY)
    kite.set_access_token(token)
    log.info(f"Kite api_key in use: {API_KEY[:4]}…{API_KEY[-3:]}  "
             f"(if this shows br9m…8nvvywnl, .env.local didn't load — set $env:KITE_API_KEY)")

    log.info("Loading Kite NSE instruments...")
    instruments = kite.instruments("NSE")
    sym2token = {i["tradingsymbol"]: i["instrument_token"] for i in instruments if i["segment"] == "NSE"}
    log.info(f"  {len(sym2token)} NSE instruments")

    end = date.today()
    start = end - timedelta(days=365 * YEARS)

    ok = miss = 0
    for sym, name, _i, _ig, _m in missing:
        tok = sym2token.get(sym) or sym2token.get(f"{sym}-EQ")
        if not tok:
            log.warning(f"  ✗ {sym}: no Kite NSE instrument token — skipped")
            miss += 1
            continue

        total = 0
        cur_from = start
        while cur_from < end:
            cur_to = min(cur_from + timedelta(days=CHUNK_DAYS), end)
            try:
                candles = kite.historical_data(tok, cur_from, cur_to, "day")
                total += upsert_daily(conn, sym, candles)
            except Exception as e:
                log.warning(f"  ! {sym} {cur_from}->{cur_to}: {e}")
            time.sleep(RATE_SLEEP)
            cur_from = cur_to + timedelta(days=1)

        if total:
            ok += 1
            log.info(f"  ✓ {sym:14} {total:,} daily candles")
        else:
            miss += 1
            log.warning(f"  ✗ {sym}: no candles returned")

    conn.close()
    log.info(f"Done — {ok} backfilled, {miss} skipped/empty.")
    log.info("Next: python _scripts/compute_candle_returns.py   (fills return_3m/6m for these)")


if __name__ == "__main__":
    main()
