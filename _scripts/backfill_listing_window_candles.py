#!/usr/bin/env python3
"""backfill_listing_window_candles.py — Phase 10 data foundation (2026-07-22).

Ensures price_candles carries DAILY candles for EVERY historical IPO from
listing_date through the anchor 30-day lock-in (anchor_lock30_date, else
listing+30d). Kite daily candles are the clean truth and naturally contain
only trading days — weekends and NSE holidays are excluded by construction,
no holiday table needed.

Discipline:
  • fill-empty-only: existing (symbol,date) rows are NEVER overwritten
  • strong key: COALESCE(nse_symbol, symbol) upper-cased, exact match
  • OHLC sanity gate (same as backfill_ipo_ohlc): invalid candles are
    SKIPPED and logged, never written
  • cost: Kite historical API is included in the existing Kite Connect app
    subscription — zero incremental spend; rate-limited politely (0.35s)

Run (VM):
  venv/bin/python _scripts/refresh_kite_token.py     # fresh token first
  venv/bin/python _scripts/backfill_listing_window_candles.py --dry-run
  venv/bin/python _scripts/backfill_listing_window_candles.py --apply
  venv/bin/python _scripts/backfill_listing_window_candles.py --apply --symbol SBIFUNDS
"""
import argparse
import datetime
import os
import sys
import time

API_KEY = os.environ.get("KITE_API_KEY", "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--symbol", help="one NSE symbol only")
    ap.add_argument("--limit", type=int, default=0, help="cap IPOs this run (rate-limit friendly)")
    a = ap.parse_args()
    if not a.apply and not a.dry_run:
        a.dry_run = True

    import psycopg2
    from kiteconnect import KiteConnect

    db = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not db:
        sys.exit("DATABASE_URL not set")
    if not API_KEY:
        sys.exit("KITE_API_KEY not set")
    conn = psycopg2.connect(db, connect_timeout=20)
    cur = conn.cursor()
    cur.execute("SELECT value FROM platform_config WHERE key = 'kite_access_token'")
    row = cur.fetchone()
    if not row:
        sys.exit("No kite_access_token in DB. Run: python _scripts/refresh_kite_token.py")
    kite = KiteConnect(api_key=API_KEY)
    kite.set_access_token(row[0])
    imap = {i["tradingsymbol"]: i["instrument_token"] for i in kite.instruments("NSE")}

    # Eligible universe (LOCKED rule), window = listing -> lock-in.
    cur.execute("""
        SELECT UPPER(COALESCE(NULLIF(btrim(nse_symbol), ''), btrim(symbol))) AS sym,
               listing_date,
               COALESCE(anchor_lock30_date, (listing_date + INTERVAL '30 days')::date) AS lock30
        FROM ipo_intelligence
        WHERE COALESCE(is_sme, false) = false
          AND (issue_size_cr IS NULL OR issue_size_cr >= 200)
          AND company_name !~* '\\y(REIT|InvIT)\\y'
          AND listing_date IS NOT NULL
          AND listing_date <= (NOW() AT TIME ZONE 'Asia/Kolkata')::date
          AND COALESCE(NULLIF(btrim(nse_symbol), ''), NULLIF(btrim(symbol), '')) IS NOT NULL
        ORDER BY listing_date DESC
    """)
    ipos = [r for r in cur.fetchall() if not a.symbol or r[0] == a.symbol.upper()]
    print(f"eligible IPO windows: {len(ipos)}")

    written = skipped_invalid = missing_token = already_full = fetched = 0
    for n, (sym, ld, lock30) in enumerate(ipos):
        if a.limit and fetched >= a.limit:
            print(f"--limit {a.limit} reached — rerun to continue")
            break
        tok = imap.get(sym)
        if tok is None:
            missing_token += 1
            print(f"  ! {sym:14} not on NSE instrument list (delisted/renamed?) — needs manual map")
            continue
        # Gap check first: expected trading days ~ (lock30-ld)*5/7; if the
        # window already has >= that many rows minus tolerance, skip the fetch.
        cur.execute("""SELECT COUNT(*) FROM price_candles
                       WHERE UPPER(symbol) = %s AND date BETWEEN %s AND %s""", (sym, ld, lock30))
        have = cur.fetchone()[0]
        expect_min = max(1, int((lock30 - ld).days * 5 / 7) - 3)
        if have >= expect_min:
            already_full += 1
            continue
        try:
            candles = kite.historical_data(tok, ld, min(lock30, datetime.date.today()), "day")
        except Exception as e:
            print(f"  ! {sym:14} historical fetch failed: {e}")
            continue
        fetched += 1
        time.sleep(0.35)  # polite: ~3 req/s ceiling
        for c in candles:
            d = c["date"].date() if hasattr(c["date"], "date") else c["date"]
            o, h, lo, cl, v = c["open"], c["high"], c["low"], c["close"], c.get("volume", 0)
            if not (o and o > 0 and h >= max(o, cl) and lo <= min(o, cl) and h >= lo):
                skipped_invalid += 1
                print(f"    x {sym} {d} invalid OHLC skipped: o={o} h={h} l={lo} c={cl}")
                continue
            if a.apply:
                cur.execute("""INSERT INTO price_candles (symbol, date, open, high, low, close, volume)
                               VALUES (%s,%s,%s,%s,%s,%s,%s)
                               ON CONFLICT (symbol, date) DO NOTHING""", (sym, d, o, h, lo, cl, v))
                written += 1
        if (n + 1) % 25 == 0:
            print(f"  … {n+1}/{len(ipos)} windows checked")
            if a.apply:
                conn.commit()
    if a.apply:
        conn.commit()
    print(f"\nRESULT windows={len(ipos)} already_full={already_full} fetched={fetched} "
          f"rows_written={written} invalid_skipped={skipped_invalid} no_token={missing_token} "
          f"({'APPLIED' if a.apply else 'DRY-RUN'})")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
