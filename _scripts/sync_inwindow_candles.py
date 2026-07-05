#!/usr/bin/env python3
"""
sync_inwindow_candles.py — the missing pipeline piece: writes daily candles into
price_candles for every IPO in its post-listing window (listing_date .. +45d).

Why this exists: the nightly step labeled "backfill candles (new IPOs)" runs
backfill_ipo_ohlc.py, which only updates listing-day FIELDS in ipo_intelligence
and never inserts price_candles rows. Result: fresh listings have no candles,
so floor/ceiling (first-5-session low/high) can't be computed. This script is
the actual candle writer for the in-window universe.

Universe: ipo_intelligence rows with a symbol and listing_date within 45 days.
Source:   Kite historical (same token as the rest of the pipeline).
Write:    INSERT ... ON CONFLICT (symbol,date) DO UPDATE — same convention as
          backfill_price_candles.py. Value-sanity before commit.

  venv/bin/python _scripts/sync_inwindow_candles.py
"""
import os, sys, datetime as dt
DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
API_KEY = os.environ.get("KITE_API_KEY")

def sane(o, h, l, c):
    try:
        o, h, l, c = float(o), float(h), float(l), float(c)
    except (TypeError, ValueError):
        return False
    return 0 < l <= min(o, c) and max(o, c) <= h and h < 1_000_000

def main():
    if not DB: sys.exit("DATABASE_URL not set")
    import psycopg2, psycopg2.extras
    conn = psycopg2.connect(DB, connect_timeout=20); cur = conn.cursor()
    cur.execute("SELECT value FROM platform_config WHERE key='kite_access_token'")
    row = cur.fetchone()
    if not row or not row[0] or not API_KEY:
        print("no kite token/key — skipping (non-fatal; next run retries)"); return
    from kiteconnect import KiteConnect
    kite = KiteConnect(api_key=API_KEY); kite.set_access_token(row[0])

    cur.execute("""SELECT DISTINCT UPPER(COALESCE(NULLIF(nse_symbol,''), symbol)) AS sym,
                          listing_date
                   FROM ipo_intelligence
                   WHERE listing_date IS NOT NULL
                     AND listing_date >= CURRENT_DATE - 45
                     AND listing_date <= CURRENT_DATE
                     AND COALESCE(NULLIF(nse_symbol,''), symbol) IS NOT NULL""")
    ipos = cur.fetchall()
    print(f"in-window IPOs: {len(ipos)}")
    if not ipos: return

    tokens = {i["tradingsymbol"]: i["instrument_token"]
              for i in kite.instruments("NSE") if i.get("instrument_type") == "EQ"}
    wrote = skipped = no_tok = 0
    for sym, ld in ipos:
        tok = tokens.get(sym)
        if not tok:
            no_tok += 1; print(f"  {sym}: not in Kite NSE list"); continue
        try:
            candles = kite.historical_data(tok, ld, dt.date.today(), "day")
        except Exception as e:
            print(f"  {sym}: kite error {e}"); continue
        rows = []
        for c in candles:
            d = c["date"].date() if hasattr(c["date"], "date") else c["date"]
            if sane(c.get("open"), c.get("high"), c.get("low"), c.get("close")):
                rows.append((sym, d, c["open"], c["high"], c["low"], c["close"],
                             int(c.get("volume") or 0)))
            else:
                skipped += 1
        if rows:
            psycopg2.extras.execute_values(cur, """
                INSERT INTO price_candles (symbol, date, open, high, low, close, volume)
                VALUES %s
                ON CONFLICT (symbol, date) DO UPDATE SET
                    open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
                    close=EXCLUDED.close, volume=EXCLUDED.volume""", rows)
            wrote += len(rows)
            print(f"  {sym}: {len(rows)} candle(s) {rows[0][1]} .. {rows[-1][1]}")
    conn.commit(); conn.close()
    print(f"DONE  wrote/updated={wrote}  insane_skipped={skipped}  not_in_kite={no_tok}")

if __name__ == "__main__":
    main()
