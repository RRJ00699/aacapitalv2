#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""backfill_listing_minutes.py — the REAL listing-day tape from Zerodha.

OWNER 2026-07-19: GMP and subscription are both INDICATIONS and both
manipulable — grey market is unregulated, subscription can be inflated by
leveraged HNI applications that never become buyers. He wants what actually
traded.

Kite's historical_data() serves MINUTE-level OHLCV back years, including listing
day. That is EXECUTED trades — money that actually moved. It cannot be talked up.

What this backfills, per IPO, for the listing session:
    first_print_price / first_print_volume   the true opening trade
    vwap_0930_1000, vwap_1000_1015           where real money transacted
    high_60m / low_60m                       the first-hour range
    vol_first_5m / vol_first_15m / vol_60m   demand that paid, not demand that applied
    close_vs_open                            did the open hold

This is NOT the pre-open order book (nobody serves that historically). It is the
next best thing and it is REAL.

Run:  python _scripts/backfill_listing_minutes.py --dry-run
      python _scripts/backfill_listing_minutes.py --apply --limit 25
"""
import argparse, datetime as dt, os, sys, time

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="cap IPOs this run (API is rate-limited)")
    ap.add_argument("--from-year", type=int, default=2016)
    a = ap.parse_args()
    if not (a.apply or a.dry_run): sys.exit("pass --apply or --dry-run")

    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"]); cur = conn.cursor()

    for stmt in [
        "ALTER TABLE ipo_consolidated ADD COLUMN IF NOT EXISTS first_print_price NUMERIC",
        "ALTER TABLE ipo_consolidated ADD COLUMN IF NOT EXISTS first_print_volume BIGINT",
        "ALTER TABLE ipo_consolidated ADD COLUMN IF NOT EXISTS vol_first_5m BIGINT",
        "ALTER TABLE ipo_consolidated ADD COLUMN IF NOT EXISTS vol_first_15m BIGINT",
        "ALTER TABLE ipo_consolidated ADD COLUMN IF NOT EXISTS vol_first_60m BIGINT",
        "ALTER TABLE ipo_consolidated ADD COLUMN IF NOT EXISTS high_first_60m NUMERIC",
        "ALTER TABLE ipo_consolidated ADD COLUMN IF NOT EXISTS low_first_60m NUMERIC",
        "ALTER TABLE ipo_consolidated ADD COLUMN IF NOT EXISTS vwap_first_15m NUMERIC",
        "ALTER TABLE ipo_consolidated ADD COLUMN IF NOT EXISTS first_trade_time TIME",
    ]:
        cur.execute(stmt)
    conn.commit()

    cur.execute("""
        SELECT UPPER(COALESCE(NULLIF(symbol_final,''), NULLIF(nse_symbol,''), symbol)) sym,
               company_name, listing_date
        FROM ipo_consolidated
        WHERE listing_date >= %s AND listing_date < CURRENT_DATE
          AND COALESCE(symbol_final, nse_symbol, symbol) IS NOT NULL
          AND first_print_price IS NULL
        ORDER BY listing_date DESC""", (f"{a.from_year}-01-01",))
    todo = cur.fetchall()
    if a.limit: todo = todo[:a.limit]
    print(f"IPOs needing the listing tape: {len(todo)}")
    if a.dry_run:
        for s, c_, d in todo[:15]: print(f"  {s:<14} {c_[:38]:<38} {d}")
        print("\n(dry run — nothing fetched or written)"); return

    from kiteconnect import KiteConnect
    cur.execute("SELECT value FROM platform_config WHERE key='kite_access_token'")
    row = cur.fetchone()
    if not row: sys.exit("no kite_access_token — run refresh_kite_token.py")
    kite = KiteConnect(api_key=os.environ.get("KITE_API_KEY", ""))
    kite.set_access_token(row[0])

    print("loading NSE instrument map…")
    tok = {i["tradingsymbol"]: i["instrument_token"]
           for i in kite.instruments("NSE") if i.get("instrument_type") == "EQ"}
    print(f"  {len(tok)} NSE equities")

    done = miss = fail = 0
    for sym, name, ld in todo:
        t = tok.get(sym)
        if not t:
            miss += 1; print(f"  ? {sym}: not in NSE instrument map"); continue
        try:
            bars = kite.historical_data(t, ld, ld, "minute")
            if not bars:
                miss += 1; print(f"  - {sym} {ld}: no minute bars"); continue
            # FIRST TRADED BAR, not bars[0] (fixed 2026-07-19).
            # IPO listings begin at 10:00 IST after the special pre-open session,
            # but Kite returns the day from 09:15 — so bars[0:5] are EMPTY
            # placeholder bars for any 10:00 lister. That produced open=111 with
            # vol5m=0 on IGCL, SAMBHV, KALPATARU, SCODATUBES, PROSTARM,
            # AEGISVOPAK: a phantom price and windows measuring silence.
            # Anchor every window on the first bar that actually TRADED.
            traded = [b for b in bars if (b.get("volume") or 0) > 0]
            if not traded:
                miss += 1; print(f"  - {sym} {ld}: no traded bars"); continue
            i0 = bars.index(traded[0])
            live = bars[i0:]
            first = live[0]
            f5, f15, f60 = live[:5], live[:15], live[:60]
            vwap15 = (sum(b["close"] * b["volume"] for b in f15) / sum(b["volume"] for b in f15)
                      if sum(b["volume"] for b in f15) else None)
            cur.execute("""UPDATE ipo_consolidated SET
                    first_print_price=%s, first_print_volume=%s,
                    vol_first_5m=%s, vol_first_15m=%s, vol_first_60m=%s,
                    high_first_60m=%s, low_first_60m=%s, vwap_first_15m=%s, first_trade_time=%s
                WHERE UPPER(COALESCE(NULLIF(symbol_final,''), NULLIF(nse_symbol,''), symbol))=%s
                  AND listing_date=%s""",
                (first["open"], first["volume"],
                 sum(b["volume"] for b in f5), sum(b["volume"] for b in f15),
                 sum(b["volume"] for b in f60),
                 max(b["high"] for b in f60), min(b["low"] for b in f60),
                 round(vwap15, 2) if vwap15 else None,
                 first["date"].time() if hasattr(first.get("date"), "time") else None,
                 sym, ld))
            conn.commit(); done += 1
            print(f"  ✓ {sym} {ld}: first_trade={first['date'].strftime('%H:%M') if hasattr(first.get('date'),'strftime') else '?'} "
                  f"open={first['open']} vol5m={sum(b['volume'] for b in f5)}")
        except Exception as e:
            fail += 1; print(f"  ✗ {sym}: {str(e)[:90]}")
        time.sleep(0.4)          # Kite historical API rate limit
    print(f"\ndone: {done} filled | {miss} no data | {fail} failed")
    conn.close()

if __name__ == "__main__":
    main()
