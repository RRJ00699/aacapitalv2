#!/usr/bin/env python3
"""
compute_smart_money.py — derives a real smart_money_score for each stock from the
institutional accumulation trend already in shareholding_history (FII + DII + MF over
the last several quarters), and writes it to stock_fundamentals.smart_money_score.

This is the SmartMoney factor the convergence engine reads. Until now it was sparse/
defaulted (scores like 15/41), dragging convergence. shareholding_history is already
populated (8 quarters), so this needs no scraping — rising institutional holding =
accumulation = high score; falling = distribution = low.

Score: 50 baseline + trend (change in institutional % across the window, weighted) +
a small level bonus (high absolute institutional interest). Clamped 0-100.

Run:  python _scripts/engines/compute_smart_money.py
Env:  DATABASE_URL (or NEON_DATABASE_URL)
"""
import os, sys, math, psycopg2, psycopg2.extras

URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
if not URL:
    sys.exit("DATABASE_URL not set")


def num(v, fb=0.0):
    try:
        return float(v) if v is not None else fb
    except (TypeError, ValueError):
        return fb


def clamp(x):
    return max(0, min(100, round(x)))


def main():
    conn = psycopg2.connect(URL); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # all quarters per symbol, oldest -> newest
    cur.execute("""
        SELECT nse_symbol, quarter,
               COALESCE(fii_pct,0) + COALESCE(dii_pct,0) + COALESCE(mf_pct,0) AS inst
        FROM shareholding_history
        WHERE nse_symbol IS NOT NULL
        ORDER BY nse_symbol, quarter ASC
    """)
    series = {}
    for r in cur.fetchall():
        series.setdefault(r["nse_symbol"], []).append(num(r["inst"]))

    if not series:
        sys.exit("shareholding_history empty — run the shareholding scrape first")

    updates = []
    for sym, inst in series.items():
        if not inst:
            continue
        latest = inst[-1]
        oldest = inst[0]
        trend = latest - oldest          # change in institutional % across the window
        # Trend is the main signal, absolute level a secondary nudge. tanh squash so
        # extremes compress smoothly toward ~95/~5 instead of piling up at the 100 clamp
        # (the old trend*3 + hard clamp pinned huge-inflow names like SUZLON all at 100).
        raw = trend * 1.5 + (latest - 35) * 0.25
        score = clamp(50 + 45 * math.tanh(raw / 20.0))
        updates.append((score, sym))

    # write back to stock_fundamentals (only rows that exist there)
    cur2 = conn.cursor()
    psycopg2.extras.execute_batch(cur2, """
        UPDATE stock_fundamentals SET smart_money_score = %s
        WHERE nse_symbol = %s
    """, updates, page_size=500)

    print(f"smart_money_score updated for {len(updates)} symbols from shareholding trend")
    top = sorted(updates, reverse=True)[:10]
    for sc, sym in top:
        print(f"  {sym:14s} smart_money={sc}")
    cur.close(); cur2.close(); conn.close()


if __name__ == "__main__":
    main()
