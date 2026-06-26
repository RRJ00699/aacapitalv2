#!/usr/bin/env python3
"""
backtest_dna_drawdown.py — the FAIR test of the DNA engine. Raw long-horizon returns inverted
(junk ripped 2021-2026), but quality's real job is DOWNSIDE PROTECTION and DURABILITY, not
melt-up returns. So per POINT-IN-TIME grade, measure: max drawdown during the hold, volatility,
return-per-unit-drawdown, and a SURVIVORSHIP check (do low-grade names delist out of the sample,
flattering their returns?). If quality shows shallower drawdowns / lower vol / fewer delistings,
DNA is validated as a RISK lens even though it doesn't predict raw return.

Run:  python _scripts/backtest_dna_drawdown.py
Env:  DATABASE_URL ; DD_HORIZONS=252,756 ; DD_DNA_MONTH=9
"""
import os, sys, warnings
import numpy as np
import pandas as pd
import psycopg2

warnings.filterwarnings("ignore")
URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
if not URL:
    sys.exit("DATABASE_URL not set")
HORIZONS = [int(x) for x in os.environ.get("DD_HORIZONS", "252,756").split(",")]
DISCLOSE_M = int(os.environ.get("DD_DNA_MONTH", "9"))
GRADE_ORDER = ["AAA+", "AAA", "AA", "A", "BBB", "BB", "B", "Avoid"]


def main():
    conn = psycopg2.connect(URL); cur = conn.cursor()
    cur.execute("SELECT symbol, as_of_year, dna_score, grade FROM financial_dna_history WHERE dna_score IS NOT NULL")
    dh = pd.DataFrame(cur.fetchall(), columns=["symbol", "as_of_year", "dna_score", "grade"])
    if dh.empty:
        sys.exit("financial_dna_history empty — run compute_financial_dna.py --history")
    dh["symbol"] = dh["symbol"].str.upper(); dh["dna_score"] = dh["dna_score"].astype(float)

    cur.execute("SELECT symbol, date, close FROM price_candles WHERE close > 0 ORDER BY symbol, date")
    px = pd.DataFrame(cur.fetchall(), columns=["symbol", "date", "close"])
    conn.close()
    px["symbol"] = px["symbol"].str.upper(); px["date"] = pd.to_datetime(px["date"])
    GLOBAL_LAST = px["date"].max()

    book, last_date = {}, {}
    for sym, g in px.groupby("symbol", sort=False):
        book[sym] = (g["date"].to_numpy("datetime64[ns]"), g["close"].to_numpy(float))
        last_date[sym] = g["date"].max()

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
            w = close[i:i + H + 1]
            if len(w) < 30:
                rec[f"dd{H}"] = np.nan; rec[f"vol{H}"] = np.nan; rec[f"ret{H}"] = np.nan
                continue
            run_max = np.maximum.accumulate(w)
            rec[f"dd{H}"] = (w / run_max - 1).min()                 # worst peak-to-trough in hold
            dr = w[1:] / w[:-1] - 1
            rec[f"vol{H}"] = np.nanstd(dr) * np.sqrt(252)           # annualized vol
            rec[f"ret{H}"] = w[-1] / w[0] - 1
        rows.append(rec)
    R = pd.DataFrame(rows)
    print(f"  {len(R):,} point-in-time grade-entries with price\n")

    def line(sub, H):
        dd = sub[f"dd{H}"].dropna(); vol = sub[f"vol{H}"].dropna(); ret = sub[f"ret{H}"].dropna()
        if len(dd) < 20:
            return None
        # return per unit of pain (median return / median |drawdown|)
        rpd = ret.median() / abs(dd.median()) if dd.median() != 0 else float("nan")
        deep = (dd <= -0.40).mean() * 100                          # share with a >40% drawdown
        return (f"N={len(dd):>5,}  maxDD(med)={dd.median()*100:6.1f}%  "
                f"vol(med)={vol.median()*100:5.1f}%  ret/DD={rpd:5.2f}  >40%DD={deep:4.1f}%")

    for H in HORIZONS:
        yr = H // 252
        print(f"── {yr}-year hold: drawdown & risk by grade ──")
        u = line(R, H)
        if u:
            print(f"  {'UNIVERSE':6}  {u}")
        for grd in GRADE_ORDER:
            s = line(R[R["grade"] == grd], H)
            if s:
                print(f"  {grd:6}  {s}")
        a = line(R[R["dna"] >= 62], H); sa = line(R[R["dna"] < 62], H)
        if a:  print(f"  {'>=A':6}  {a}")
        if sa: print(f"  {'<A':6}  {sa}")
        print()

    # ── survivorship: do low-grade names delist out of the sample? ──
    print("Survivorship — graded names whose price series ENDS early (delist/suspend proxy):")
    surv = dh.drop_duplicates("symbol").copy()
    surv["last"] = surv["symbol"].map(last_date)
    surv["stale"] = surv["last"] < (GLOBAL_LAST - pd.Timedelta(days=120))
    surv["bucket"] = pd.cut(surv["dna_score"], [-1, 36, 52, 62, 200],
                            labels=["Avoid(<36)", "B/BB(36-52)", "A/BBB(52-62)", ">=A(>=62)"])
    g = surv.groupby("bucket").agg(n=("symbol", "size"), stale=("stale", "sum"))
    g["stale_pct"] = (g["stale"] / g["n"] * 100).round(1)
    for b, row in g.iterrows():
        print(f"  {str(b):14} n={int(row['n']):>4}  delisted/stale={int(row['stale']):>3} ({row['stale_pct']}%)")
    print("\nRead honestly: DNA earns its place as a RISK lens if higher grades show SHALLOWER maxDD,")
    print("LOWER vol, and FEWER delistings. If low grades also delist far more, their raw-return")
    print("outperformance was partly survivorship. If quality protects downside, ship DNA as a risk/")
    print("conviction layer (not a return signal). If drawdowns are flat across grades too, DNA is a")
    print("pure research/explainability tool.")


if __name__ == "__main__":
    main()
