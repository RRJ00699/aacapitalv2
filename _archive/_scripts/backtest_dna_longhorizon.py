#!/usr/bin/env python3
"""
backtest_dna_longhorizon.py — the test the DNA engine was actually built for.

The convergence test proved fundamental quality doesn't help 60-DAY trade timing (quality is
priced in short-term). But the DNA engine's real thesis is identifying multi-year compounders.
So: using POINT-IN-TIME vintage grades (financial_dna_history, no look-ahead), measure forward
1yr / 2yr / 3yr returns by grade. Entry = the date a fiscal year's grade became public
(~Sept of that year). If higher grades compound faster over years — ideally monotonically —
the engine is validated as a long-term conviction tool, independent of trade timing.

Run:  python _scripts/backtest_dna_longhorizon.py
Env:  DATABASE_URL ; LH_HORIZONS=252,504,756 (1/2/3yr td) ; LH_DNA_MONTH=9 (disclosure month)
"""
import os, sys, warnings
import numpy as np
import pandas as pd
import psycopg2

warnings.filterwarnings("ignore")
URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
if not URL:
    sys.exit("DATABASE_URL not set")
HORIZONS = [int(x) for x in os.environ.get("LH_HORIZONS", "252,504,756").split(",")]
DISCLOSE_M = int(os.environ.get("LH_DNA_MONTH", "9"))
GRADE_ORDER = ["AAA+", "AAA", "AA", "A", "BBB", "BB", "B", "Avoid"]


def fwd_stats(s):
    s = s.dropna()
    if len(s) == 0:
        return "       -"
    return f"N={len(s):>5,} win={ (s>0).mean()*100:5.1f}% med={s.median()*100:6.1f}% mean={s.mean()*100:6.1f}%"


def main():
    conn = psycopg2.connect(URL); cur = conn.cursor()
    cur.execute("SELECT symbol, as_of_year, dna_score, grade FROM financial_dna_history WHERE dna_score IS NOT NULL")
    dh = pd.DataFrame(cur.fetchall(), columns=["symbol", "as_of_year", "dna_score", "grade"])
    if dh.empty:
        sys.exit("financial_dna_history empty — run: python _scripts/compute_financial_dna.py --history")
    dh["symbol"] = dh["symbol"].str.upper(); dh["dna_score"] = dh["dna_score"].astype(float)

    cur.execute("SELECT symbol, date, close FROM price_candles WHERE close > 0 ORDER BY symbol, date")
    px = pd.DataFrame(cur.fetchall(), columns=["symbol", "date", "close"])
    conn.close()
    px["symbol"] = px["symbol"].str.upper(); px["date"] = pd.to_datetime(px["date"])

    # per-symbol arrays for fast forward lookups
    book = {}
    for sym, g in px.groupby("symbol", sort=False):
        book[sym] = (g["date"].to_numpy("datetime64[ns]"), g["close"].to_numpy(float))

    rows = []
    for r in dh.itertuples(index=False):
        b = book.get(r.symbol)
        if b is None:
            continue
        dates, close = b
        entry = np.datetime64(f"{r.as_of_year}-{DISCLOSE_M:02d}-28")
        i = int(np.searchsorted(dates, entry))
        if i >= len(close):
            continue
        rec = {"symbol": r.symbol, "year": r.as_of_year, "grade": r.grade, "dna": r.dna_score}
        for H in HORIZONS:
            rec[f"f{H}"] = close[i + H] / close[i] - 1 if i + H < len(close) else np.nan
        rows.append(rec)
    R = pd.DataFrame(rows)
    print(f"  {len(R):,} point-in-time grade-entries with price data "
          f"(vintage grades entered ~{DISCLOSE_M}/of fiscal year)\n")

    # ── by grade bucket, each horizon ──
    print("Forward returns by POINT-IN-TIME grade (no look-ahead):")
    for H in HORIZONS:
        yr = H // 252
        print(f"\n── {yr}-year forward ({H}td) ──")
        print(f"  {'UNIVERSE':6}  {fwd_stats(R[f'f{H}'])}")
        for grd in GRADE_ORDER:
            sub = R[R['grade'] == grd][f"f{H}"]
            if len(sub.dropna()) >= 20:
                print(f"  {grd:6}  {fwd_stats(sub)}")
        a = R[R['dna'] >= 62][f"f{H}"]; sa = R[R['dna'] < 62][f"f{H}"]
        print(f"  {'>=A':6}  {fwd_stats(a)}")
        print(f"  {'<A':6}  {fwd_stats(sa)}")
        if len(a.dropna()) and len(sa.dropna()):
            lift = (a.median() - sa.median()) * 100
            print(f"  A-minus-subA median lift: {lift:+.1f} pts over {yr}yr")

    # ── robustness: A vs sub-A by vintage year, headline horizon ──
    H = HORIZONS[0]; yr = H // 252
    print(f"\nRobustness — >=A vs <A median {yr}yr return, by vintage year:")
    for y, g in R.groupby("year"):
        a = g[g['dna'] >= 62][f"f{H}"].dropna(); sa = g[g['dna'] < 62][f"f{H}"].dropna()
        if len(a) >= 15 and len(sa) >= 15:
            tag = "A wins" if a.median() > sa.median() else "A loses"
            print(f"  {y}: A {a.median()*100:6.1f}% (n={len(a):>4})  vs  sub-A {sa.median()*100:6.1f}% (n={len(sa):>4})   {tag}")

    print("\nRead honestly: the engine is validated as a LONG-TERM conviction tool only if higher")
    print("grades compound faster — ideally a monotonic ladder (AAA>AA>A>BBB...) and >=A beating")
    print("<A in MOST vintage years, not one. A flat/inverted ladder means quality is fully priced")
    print("and DNA is a research/explainability tool, not a return predictor.")


if __name__ == "__main__":
    main()
