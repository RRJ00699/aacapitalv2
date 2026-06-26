#!/usr/bin/env python3
"""
compute_candle_returns.py — derive return_3m / return_6m for every symbol from
price_candles and write them into stock_fundamentals. Replaces the sparse,
manually-sourced return columns the scorecard's Momentum sub-score reads.

Why: stock_fundamentals.return_3m / return_6m are null for many symbols (a known
open item). price_candles now holds the full daily history, so we can compute
these honestly and keep them fresh — run this right after the daily candle sync.

Method: trading-day offsets off each symbol's own close series —
    return_3m = last_close / close_63_sessions_ago  - 1   (≈ 3 months)
    return_6m = last_close / close_126_sessions_ago - 1   (≈ 6 months)
Symbols without enough history leave the value NULL (never fabricated).

Only touches columns verified to exist: return_3m, return_6m. nse_symbol is the
join key in stock_fundamentals; price_candles keys on symbol.

Run:  python _scripts/compute_candle_returns.py
Env:  DATABASE_URL (or NEON_DATABASE_URL)
"""
import os
import sys
import logging
import psycopg2
import psycopg2.extras

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger()

URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
if not URL:
    sys.exit("DATABASE_URL not set")

TD_3M = 63    # ~3 months of trading sessions
TD_6M = 126   # ~6 months of trading sessions


def pct_return(closes, offset):
    """last close vs the close `offset` sessions ago, as a percent; None if short."""
    if len(closes) <= offset:
        return None
    now, then = closes[-1], closes[-1 - offset]
    if not then:
        return None
    return round((now / then - 1) * 100, 2)


def main():
    conn = psycopg2.connect(URL)
    conn.autocommit = False
    cur = conn.cursor()

    # Pull (symbol, close) for the whole table in symbol/date order and stream-group
    # in Python — one pass, no per-symbol round-trips.
    log.info("Reading price_candles closes…")
    cur.execute("""
        SELECT symbol, close
        FROM price_candles
        WHERE close IS NOT NULL
        ORDER BY symbol, date ASC
    """)

    updates = []          # (return_3m, return_6m, symbol)
    cur_sym = None
    closes = []

    def flush(sym, series):
        if not sym or not series:
            return
        r3 = pct_return(series, TD_3M)
        r6 = pct_return(series, TD_6M)
        if r3 is not None or r6 is not None:
            updates.append((r3, r6, sym))

    for sym, close in cur:
        if sym != cur_sym:
            flush(cur_sym, closes)
            cur_sym, closes = sym, []
        closes.append(float(close))
    flush(cur_sym, closes)   # last symbol

    log.info(f"Computed returns for {len(updates):,} symbols. Writing to stock_fundamentals…")

    # Write via a temp table + single UPDATE … FROM join (fast, one statement).
    wcur = conn.cursor()
    wcur.execute("""
        CREATE TEMP TABLE _ret (symbol TEXT PRIMARY KEY, r3 NUMERIC, r6 NUMERIC) ON COMMIT DROP
    """)
    psycopg2.extras.execute_values(
        wcur,
        "INSERT INTO _ret (r3, r6, symbol) VALUES %s",
        updates,
        template="(%s, %s, %s)",
    )
    wcur.execute("""
        UPDATE stock_fundamentals sf
        SET return_3m = _ret.r3,
            return_6m = _ret.r6
        FROM _ret
        WHERE sf.nse_symbol = _ret.symbol
    """)
    matched = wcur.rowcount
    conn.commit()

    log.info(f"Updated {matched:,} stock_fundamentals rows (return_3m / return_6m).")
    if matched < len(updates):
        log.info(f"Note: {len(updates) - matched:,} computed symbols had no matching "
                 f"nse_symbol in stock_fundamentals (candles exist but not in the 1,400 universe).")

    wcur.close()
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
