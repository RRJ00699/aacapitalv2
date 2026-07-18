#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""backtest_journey_exits.py — does the Journey screen's exit discipline
(lock8/trail12) actually beat naive holding? The Journey screen's whole promise
is "hold, the rule protects you, don't panic-sell" — this quantifies it.

Window: 2021-01-01 -> now (clean-data era; spans 2021 euphoria, 2022-23
drawdown, 2024-25 normalization — a full cycle, not just a bull run).

Strategies compared, entry = listing-day open, per IPO:
  NAIVE_D10   : hold, sell at day-10 close (the ipo_score horizon baseline)
  NAIVE_D30   : hold, sell at day-30 close (the anchor first-lock-in window)
  LOCK8_TRAIL12: arm a floor once +8%; trail 12% off the running peak; the
                 Journey rule. Exit at first intraday breach of the active stop.
  BUY_HOLD_90 : hold 90 sessions (upper bound / survivorship reference)

Realistic fills: trail/floor breaches checked against intraday LOW (not close),
so we don't flatter the rule by ignoring wicks. Return = exit/entry - 1.

ACCEPTANCE: the Journey rule must beat NAIVE_D10 on BOTH median return AND
downside (worse-decile) — protecting the panic-seller is the point. If it only
wins on mean, that's melt-up capture, not discipline; report it honestly.

Run:  DATABASE_URL=... python _scripts/backtest_journey_exits.py
      [START=2021-01-01]  [LOCK=8]  [TRAIL=12]
"""
import os, sys, statistics as st
from datetime import date

def _num(x):
    try: return float(x)
    except Exception: return None

def simulate(candles, lock_pct, trail_pct, floor_pct=3.0):
    """candles: [(date, open, high, low, close)] listing-day first, chronological.
    Returns dict of per-strategy exit return fraction."""
    if not candles:
        return None
    entry = _num(candles[0][1])  # listing-day OPEN
    if not entry or entry <= 0:
        return None
    n = len(candles)
    close_d10 = _num(candles[min(9, n - 1)][4])
    close_d30 = _num(candles[min(29, n - 1)][4])
    close_d90 = _num(candles[min(89, n - 1)][4])

    # LOCK/FLOOR/TRAIL — the documented rule: arm at +lock%, floor at +floor%,
    # trail trail% off peak.
    # TWO BUGS FIXED 2026-07-18 (first run produced median EXACTLY 0.0% every
    # sweep — the tell):
    #  1. SAME-BAR arm-and-exit: the old loop set peak from TODAY's high then
    #     checked TODAY's low against it. A listing-day stock that spikes +8%
    #     and dips intraday exited at entry on day 1 -> a pile of exactly-0.0%
    #     results. You cannot know intraday sequence from a daily candle, so the
    #     stop is now evaluated against PRIOR bars' peak only.
    #  2. Floor was entry (0% locked) instead of the documented +3%.
    peak = entry
    floor_armed = False
    exit_px = None
    for i, (_, o, hi, lo, cl) in enumerate(candles):
        o, hi, lo, cl = _num(o), _num(hi), _num(lo), _num(cl)
        if hi is None or lo is None:
            continue
        # 1) stop check FIRST, using the peak established by PREVIOUS bars
        if floor_armed:
            stop = max(entry * (1 + floor_pct / 100),
                       peak * (1 - trail_pct / 100))
            if lo <= stop:
                # gap-down honesty: if the bar OPENED below the stop, you fill
                # at the open, not the (better) stop price
                exit_px = min(stop, o) if (o is not None and o < stop) else stop
                break
        # 2) then update peak / arm the floor with THIS bar (effective tomorrow)
        peak = max(peak, hi)
        if not floor_armed and (peak / entry - 1) >= lock_pct / 100:
            floor_armed = True
    if exit_px is None:                                   # never stopped -> day-90 close
        exit_px = close_d90 or _num(candles[-1][4])

    def r(px): return (px / entry - 1) if px else None
    return {
        "NAIVE_D10": r(close_d10),
        "NAIVE_D30": r(close_d30),
        "LOCK8_TRAIL12": r(exit_px),
        "BUY_HOLD_90": r(close_d90),
    }

def summarize(rows, keys):
    print(f"\n{'strategy':<16}{'n':>5}{'mean%':>9}{'median%':>9}{'p10%':>8}{'p90%':>8}{'win%':>7}")
    print("-" * 62)
    out = {}
    for k in keys:
        vals = sorted(v[k] * 100 for v in rows if v.get(k) is not None)
        if not vals: continue
        n = len(vals)
        p10 = vals[max(0, int(n * 0.10) - 1)]
        p90 = vals[min(n - 1, int(n * 0.90))]
        win = 100 * sum(1 for x in vals if x > 0) / n
        out[k] = {"mean": st.mean(vals), "median": st.median(vals), "p10": p10, "win": win, "n": n}
        print(f"{k:<16}{n:>5}{st.mean(vals):>9.1f}{st.median(vals):>9.1f}{p10:>8.1f}{p90:>8.1f}{win:>7.1f}")
    return out

def main():
    url = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL not set")
    start = os.environ.get("START", "2021-01-01")
    lock = float(os.environ.get("LOCK", "8"))
    trail = float(os.environ.get("TRAIL", "12"))
    floor = float(os.environ.get("FLOOR", "3"))  # documented rule: floor at +3%
    import psycopg2
    conn = psycopg2.connect(url); cur = conn.cursor()
    # IPOs listed since START with clean candles
    cur.execute("""
        SELECT DISTINCT UPPER(REGEXP_REPLACE(COALESCE(symbol_final, nse_symbol, symbol), '\\.NS$','')) AS sym,
               listing_date
        FROM ipo_consolidated
        WHERE listing_date >= %s AND listing_date IS NOT NULL
          AND COALESCE(symbol_final, nse_symbol, symbol) IS NOT NULL
        ORDER BY listing_date
    """, (start,))
    ipos = cur.fetchall()
    rows = []
    used = 0
    for sym, ld in ipos:
        cur.execute("""
            SELECT date, open, high, low, close FROM price_candles
            WHERE UPPER(REGEXP_REPLACE(symbol,'\\.NS$','')) = %s
              AND date >= %s AND close > 0
            ORDER BY date LIMIT 95
        """, (sym, ld))
        c = cur.fetchall()
        if len(c) < 10:   # need at least the D10 horizon
            continue
        res = simulate(c, lock, trail, floor)
        if res and res.get("NAIVE_D10") is not None:
            rows.append(res); used += 1
    conn.close()

    print(f"\nJOURNEY EXIT BACKTEST — listings {start}..now")
    print(f"n={used} IPOs with clean candles | rule: arm +{lock:.0f}% / floor +{floor:.0f}% / trail {trail:.0f}%")
    s = summarize(rows, ["NAIVE_D10", "NAIVE_D30", "LOCK8_TRAIL12", "BUY_HOLD_90"])

    # ACCEPTANCE: rule beats NAIVE_D10 on median AND downside (p10)
    if "LOCK8_TRAIL12" in s and "NAIVE_D10" in s:
        r, b = s["LOCK8_TRAIL12"], s["NAIVE_D10"]
        med_ok = r["median"] >= b["median"]
        down_ok = r["p10"] >= b["p10"]
        print(f"\nACCEPTANCE vs NAIVE_D10:")
        print(f"  median: rule {r['median']:.1f}% vs naive {b['median']:.1f}%  ->  {'PASS' if med_ok else 'FAIL'}")
        print(f"  downside (p10): rule {r['p10']:.1f}% vs naive {b['p10']:.1f}%  ->  {'PASS' if down_ok else 'FAIL'}")
        print(f"  VERDICT: {'PASS — the exit discipline earns its promise' if (med_ok and down_ok) else 'FAIL — rule does not protect better; revisit before trusting Journey copy'}")

if __name__ == "__main__":
    main()
