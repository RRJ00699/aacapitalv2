#!/usr/bin/env python3
"""
backtest_convergence.py — does stacking INDEPENDENT factors on the breakout signal beat the
~59% price-only ceiling? The regime test proved tightening price filters doesn't help; the
honest lever is uncorrelated information. We test the breakout setup gated by:

  • SMART MONEY (clean, point-in-time): was institutional holding (FII+DII+MF) RISING as of
    the most recent DISCLOSED quarter before the signal (entered SM_LAG days after quarter-end,
    so no look-ahead). Trustworthy — but shareholding_history is only ~2yr deep, so this
    subset is recent-only and smaller.
  • DNA QUALITY (look-ahead caveat): the company's CURRENT financial_dna grade. Because DNA is
    computed from the full 10yr history, applying it to old signals is survivorship/look-ahead.
    Treat as a SUGGESTIVE "quality tilt", not a tradeable result. (Point-in-time DNA = future work.)

Base setup: near5 + vol_exp + above200 (the 59% breakout). Forward horizon 60td.
Run:  python _scripts/backtest_convergence.py
Env:  DATABASE_URL ; CV_FWD=60 ; CV_LAG=45 (disclosure lag) ; CV_DNA_MIN=62 (A grade) ;
      CV_MIN_HISTORY=220
"""
import os, sys, re, warnings
import numpy as np
import pandas as pd
import psycopg2

warnings.filterwarnings("ignore")
URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
if not URL:
    sys.exit("DATABASE_URL not set")
FWD = int(os.environ.get("CV_FWD", "60"))
LAG = int(os.environ.get("CV_LAG", "45"))
DNA_MIN = float(os.environ.get("CV_DNA_MIN", "62"))
MIN_HISTORY = int(os.environ.get("CV_MIN_HISTORY", "220"))
PIT = "--pit" in sys.argv                                  # point-in-time vintage DNA (honest test)
DNA_DISCLOSE_M = int(os.environ.get("CV_DNA_MONTH", "9"))  # month a fiscal year's grade becomes public

QEND = {"1": (6, 30), "2": (9, 30), "3": (12, 31), "4": (3, 31)}  # Indian fiscal quarter-ends


def ema(a, span):
    return pd.Series(a).ewm(span=span, adjust=False).mean().to_numpy()


def breakout_signals(df):
    """Return rows where near5 + vol_exp + above200 fires, with fwd60 return."""
    c = df["close"].to_numpy(float).copy(); h = df["high"].to_numpy(float); v = df["volume"].to_numpy(float)
    n = len(c); c[c <= 0] = np.nan
    e200 = ema(c, 200)
    va = pd.Series(v).rolling(20).mean().shift(1).to_numpy()
    vr = np.divide(v, va, out=np.ones_like(v), where=(va > 0))
    roll_hi = pd.Series(h).rolling(252, min_periods=60).max().to_numpy()
    near = np.divide(roll_hi - c, roll_hi, out=np.full(n, np.nan), where=roll_hi > 0) * 100
    fwd = np.full(n, np.nan)
    if n > FWD:
        fwd[:-FWD] = (c[FWD:] / c[:-FWD] - 1) * 100
    sig = (near <= 5) & (vr >= 1.5) & (c > e200)
    sig[:MIN_HISTORY] = False
    idx = np.where(sig & np.isfinite(fwd))[0]
    return pd.DataFrame({"date": df["date"].values[idx], "fwd": fwd[idx]})


def q_to_date(q):
    m = re.match(r"(\d{4})Q([1-4])", str(q).strip())
    if not m:
        return pd.NaT
    mo, day = QEND[m.group(2)]
    return pd.Timestamp(year=int(m.group(1)), month=mo, day=day)


def stats(s, label):
    n = len(s)
    if n == 0:
        return f"{label:42} N=      0"
    win = (s > 0).mean() * 100
    return f"{label:42} N={n:>8,}  win={win:5.1f}%  med={s.median():5.2f}%  worst10={s.quantile(.10):6.1f}%"


def main():
    conn = psycopg2.connect(URL); cur = conn.cursor()

    cur.execute("SELECT symbol, date, high, low, close, volume FROM price_candles ORDER BY symbol, date")
    px = pd.DataFrame(cur.fetchall(), columns=["symbol", "date", "high", "low", "close", "volume"])
    sig_parts = []
    for sym, g in px.groupby("symbol", sort=False):
        if len(g) < MIN_HISTORY + FWD:
            continue
        s = breakout_signals(g.reset_index(drop=True))
        if len(s):
            s["symbol"] = str(sym).upper()
            sig_parts.append(s)
    S = pd.concat(sig_parts, ignore_index=True)
    S["date"] = pd.to_datetime(S["date"]); S["year"] = S["date"].dt.year
    print(f"  breakout signals: {len(S):,}  (near5+vol_exp+above200, fwd={FWD}td)")

    # DNA factor — current snapshot (default) OR point-in-time vintage (--pit)
    if PIT:
        cur.execute("SELECT symbol, as_of_year, dna_score FROM financial_dna_history WHERE dna_score IS NOT NULL")
        dh = pd.DataFrame(cur.fetchall(), columns=["symbol", "as_of_year", "dna_score"])
        if dh.empty:
            sys.exit("financial_dna_history is empty — run: python _scripts/compute_financial_dna.py --history")
        dh["symbol"] = dh["symbol"].str.upper()
        dh["dna_score"] = dh["dna_score"].astype(float)
        # vintage becomes usable only after results are disclosed (~Sept of the fiscal year for
        # Mar year-ends — most Indian names). Configurable via CV_DNA_MONTH.
        dh["avail"] = pd.to_datetime(dict(year=dh["as_of_year"].astype(int),
                                          month=DNA_DISCLOSE_M, day=28)).astype("datetime64[ns]")
        dh = dh.dropna(subset=["avail"]).sort_values("avail")
        Ssort = S.sort_values("date").copy()
        Ssort["date"] = Ssort["date"].astype("datetime64[ns]")
        S = pd.merge_asof(Ssort, dh[["symbol", "avail", "dna_score"]], left_on="date", right_on="avail",
                          by="symbol", direction="backward").rename(columns={"dna_score": "dna"})
        print(f"  DNA mode: POINT-IN-TIME (vintage grade, disclosed ~{DNA_DISCLOSE_M}mo after year-end). "
              f"matched {S['dna'].notna().sum():,} ({S['dna'].notna().mean()*100:.0f}%)")
    else:
        cur.execute("SELECT symbol, dna_score FROM financial_dna")
        dna = {str(r[0]).upper(): float(r[1]) for r in cur.fetchall() if r[1] is not None}
        S["dna"] = S["symbol"].map(dna)
        print("  DNA mode: current snapshot (LOOK-AHEAD; use --pit for the honest test)")

    # smart money: institutional accumulation, point-in-time with disclosure lag
    cur.execute("""SELECT nse_symbol, quarter,
                          COALESCE(fii_pct,0)+COALESCE(dii_pct,0)+COALESCE(mf_pct,0) AS inst
                   FROM shareholding_history WHERE quarter IS NOT NULL AND nse_symbol IS NOT NULL""")
    sh = pd.DataFrame(cur.fetchall(), columns=["symbol", "quarter", "inst"])
    conn.close()
    sh["symbol"] = sh["symbol"].str.upper()
    sh["inst"] = sh["inst"].astype(float)
    sh["qdate"] = sh["quarter"].apply(q_to_date)
    sh = sh.dropna(subset=["qdate"]).sort_values(["symbol", "qdate"])
    sh["accum"] = sh.groupby("symbol")["inst"].diff() > 0        # holding rose vs prior quarter
    sh["entry_date"] = sh["qdate"] + pd.Timedelta(days=LAG)       # disclosed/tradeable only after lag
    sh = sh.dropna(subset=["accum"]).sort_values("entry_date")

    # as-of join: each signal gets the latest disclosed accumulation state.
    # Force identical datetime resolution — DB dates arrive as [s], computed dates as [us].
    S = S.sort_values("date")
    S["date"] = S["date"].astype("datetime64[ns]")
    sh["entry_date"] = sh["entry_date"].astype("datetime64[ns]")
    sh = sh.sort_values("entry_date")
    M = pd.merge_asof(S, sh[["symbol", "entry_date", "accum"]], left_on="date", right_on="entry_date",
                      by="symbol", direction="backward")
    have_sm = M["accum"].notna()
    print(f"  signals with smart-money disclosure available: {have_sm.sum():,} "
          f"({have_sm.mean()*100:.0f}%; shareholding is only ~2yr deep)\n")

    base = M["fwd"]
    acc = M["accum"]
    is_acc = acc.eq(True)        # NaN-safe: unmatched rows are neither acc nor dist
    is_dist = acc.eq(False)
    print("=" * 92)
    print(stats(base, "BREAKOUT only (baseline of the signal)"))
    print("-" * 92)
    print("QUALITY TILT (DNA = current snapshot -> LOOK-AHEAD; suggestive only):")
    print(stats(M.loc[M["dna"] >= DNA_MIN, "fwd"], f"  breakout + DNA>={DNA_MIN:.0f} (A+)"))
    print(stats(M.loc[M["dna"] < DNA_MIN, "fwd"],  f"  breakout + DNA<{DNA_MIN:.0f}"))
    print("-" * 92)
    print("SMART MONEY (point-in-time, disclosure-lagged -> TRUSTWORTHY; recent ~2yr only):")
    print(stats(M.loc[is_acc, "fwd"],  "  breakout + accumulating"))
    print(stats(M.loc[is_dist, "fwd"], "  breakout + distributing"))
    print("-" * 92)
    print("CONVERGENCE (both):")
    print(stats(M.loc[is_acc & (M["dna"] >= DNA_MIN), "fwd"], "  breakout + accumulating + DNA>=A"))
    print("=" * 92)

    # per-year for the clean smart-money dimension
    sm_acc = M[is_acc]
    if len(sm_acc):
        print("\nPer-year — breakout + accumulating (clean):")
        for y, gy in sm_acc.groupby("year"):
            if len(gy) >= 40:
                b = base[M["year"] == y]
                print(f"  {y}  N={len(gy):>5,}  win={(gy['fwd']>0).mean()*100:5.1f}%  "
                      f"(vs breakout-all {((b>0).mean()*100):5.1f}%)  med={gy['fwd'].median():5.2f}%")
    print("\nRead honestly: SMART-MONEY rows are point-in-time clean — trust those. DNA rows carry")
    print("look-ahead (current grade on old signals) — a hint that quality helps, not a tradeable")
    print("number until we compute point-in-time DNA. A real lift = accumulating beats breakout-only")
    print("win% by a wide margin on a healthy N.")


if __name__ == "__main__":
    main()
