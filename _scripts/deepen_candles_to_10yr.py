#!/usr/bin/env python3
"""
deepen_candles_to_10yr.py — bring every shallow symbol in price_candles up to a full
~10yr daily history from Kite. The CSV backfill path is dead (no local CSVs), and most
of the base universe is only ~4-5yr deep, so we pull the missing depth from Kite — the
same chunked approach that just worked for the 33 large-caps.

Self-scoping: it finds symbols whose earliest candle is more recent than ~10yr ago and
backfills only those. Already-deep symbols (the 33 large-caps) are skipped automatically.
Idempotent: ON CONFLICT (symbol,date) DO UPDATE, so re-running is safe.

Run AFTER a fresh token (the daily 08:00 refresh, or refresh_kite_token.py). Token is
read from Neon platform_config. ~2 Kite calls per shallow symbol, paced ~3/sec.

Run:  python _scripts/deepen_candles_to_10yr.py
      python _scripts/deepen_candles_to_10yr.py --dry-run        # just count the shallow ones
      python _scripts/deepen_candles_to_10yr.py --years 10
Env:  DATABASE_URL (Neon); KITE_API_KEY (defaults to app key); .env.local auto-loaded.
"""
import os
import sys
import time
import argparse
import logging
from datetime import date, timedelta

import psycopg2
import psycopg2.extras

# load .env.local BEFORE reading KITE_API_KEY, like kite-sync-candles.py
try:
    from dotenv import load_dotenv
    load_dotenv(".env.local")
    load_dotenv(".env")
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger()

URL        = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
API_KEY    = os.environ.get("KITE_API_KEY", "br9m41pn8nvvywnl")
CHUNK_DAYS = 1900            # < Kite's 2000-day/request cap for daily candles
RATE_SLEEP = 0.35            # ~3 req/sec

if not URL:
    sys.exit("DATABASE_URL not set")


def get_access_token(conn) -> str:
    try:
        cur = conn.cursor()
        cur.execute("SELECT value FROM platform_config WHERE key='kite_access_token'")
        row = cur.fetchone(); cur.close()
        if row and row[0] and row[0] != "not_set_yet":
            log.info("Kite token from Neon platform_config")
            return row[0]
    except Exception as e:
        log.warning(f"platform_config token fetch failed: {e}")
    tok = os.environ.get("KITE_ACCESS_TOKEN", "")
    if tok:
        return tok
    sys.exit("No Kite access token. Run the token refresh first.")


def find_shallow(conn, years: int):
    """Symbols whose earliest candle is more recent than ~years ago (need deepening)."""
    floor = (date.today() - timedelta(days=int(years * 365.25) - 45)).isoformat()  # 45d grace
    cur = conn.cursor()
    cur.execute("""
        SELECT symbol, MIN(date) AS earliest, COUNT(*) AS n
        FROM price_candles
        GROUP BY symbol
        HAVING MIN(date) > %s
        ORDER BY symbol
    """, (floor,))
    rows = cur.fetchall(); cur.close()
    return rows, floor


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
    conn.commit(); cur.close()
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=10, help="Target history depth (default 10)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(URL)
    shallow, floor = find_shallow(conn, args.years)
    log.info(f"{len(shallow)} symbols are shallower than {args.years}yr (earliest after {floor})")

    if args.dry_run:
        for sym, earliest, n in shallow[:25]:
            log.info(f"   {sym:14} earliest {earliest}  ({n} candles)")
        if len(shallow) > 25:
            log.info(f"   … and {len(shallow)-25} more")
        log.info("Dry run — no writes.")
        conn.close(); return
    if not shallow:
        log.info("Everyone already at target depth. Nothing to do.")
        conn.close(); return

    token = get_access_token(conn)
    try:
        from kiteconnect import KiteConnect
    except ImportError:
        sys.exit("pip install kiteconnect")
    kite = KiteConnect(api_key=API_KEY)
    kite.set_access_token(token)
    log.info(f"Kite api_key in use: {API_KEY[:4]}…{API_KEY[-3:]}")

    log.info("Loading Kite NSE instruments…")
    instruments = kite.instruments("NSE")
    sym2token = {i["tradingsymbol"]: i["instrument_token"] for i in instruments if i["segment"] == "NSE"}
    log.info(f"  {len(sym2token)} NSE instruments")

    end = date.today()
    start = end - timedelta(days=int(args.years * 365.25))

    ok = miss = added = 0
    for idx, (sym, _earliest, _n) in enumerate(shallow, 1):
        tok = sym2token.get(sym) or sym2token.get(f"{sym}-EQ")
        if not tok:
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
            ok += 1; added += total
        else:
            miss += 1
        if idx % 100 == 0:
            log.info(f"  [{idx}/{len(shallow)}] deepened {ok} so far…")

    conn.close()
    log.info(f"Done — deepened {ok} symbols ({added:,} rows upserted), {miss} skipped (no token / empty).")
    log.info("Returns are 6-month lookback, so no need to re-run compute_candle_returns.")


if __name__ == "__main__":
    main()
