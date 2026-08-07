#!/usr/bin/env python3
"""flags_horizon_backtest.py — READ-ONLY: quality flags vs LONGER horizons.
d10 said flags don't matter (market prices the polish). But fundamentals should
bite with time: measures open -> close at session 21 (~d30) and 63 (~d90),
by flag count. Coverage-limited by candle depth; n printed honestly.
  python research/backtests/flags_horizon_backtest.py"""
import os, sys, json

def stats(rets):
    n = len(rets)
    if n < 8: return None
    s = sorted(rets)
    return n, sum(1 for r in rets if r > 0)/n*100, s[n//2]

def main():
    import psycopg2
    DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not DB: sys.exit("DATABASE_URL not set")
    cur = psycopg2.connect(DB, connect_timeout=20).cursor()
    cur.execute("""
        SELECT i.operator_risk_flags, i.listing_open,
               ARRAY_AGG(p.close ORDER BY p.date)
        FROM ipo_intelligence i
        JOIN price_candles p
          ON UPPER(p.symbol) = UPPER(COALESCE(NULLIF(i.nse_symbol,''), i.symbol))
         AND p.date >= i.listing_date
        WHERE i.operator_risk_flags IS NOT NULL AND i.listing_open > 0
          AND i.listing_date < CURRENT_DATE - 40
        GROUP BY 1, 2 HAVING COUNT(*) >= 21""")
    d30, d90 = {}, {}
    for flags, lopen, closes in cur.fetchall():
        try:
            qf = (flags if isinstance(flags, dict) else json.loads(flags)).get("qf", 0)
        except Exception:
            continue
        band = "2+ flags" if qf >= 2 else ("1 flag" if qf == 1 else "clean")
        entry = float(lopen); c = [float(x) for x in closes]
        d30.setdefault(band, []).append((c[20] - entry)/entry*100)
        if len(c) >= 63:
            d90.setdefault(band, []).append((c[62] - entry)/entry*100)
    for name, d in (("~d30 (session 21 close)", d30), ("~d90 (session 63 close)", d90)):
        print(f"\n{name}:")
        for band in ("clean", "1 flag", "2+ flags"):
            st = stats(d.get(band, []))
            print(f"  {band:9} " + (f"n={st[0]:<4} win={st[1]:5.1f}%  med={st[2]:+6.1f}" if st else "n<8 — insufficient candle depth"))
    print("\nREAD-ONLY. If flagged medians lag clean by >=5pts at n>=30 on either "
          "horizon: flags graduate to hold-context warnings on cards. Flat = context only, everywhere.")

if __name__ == "__main__":
    main()
