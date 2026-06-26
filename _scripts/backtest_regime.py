#!/usr/bin/env python3
"""
backtest_regime.py — the 10yr verdict said the breakout setups have edge ONLY in uptrends.
This gates every setup on a self-contained MARKET REGIME and grid-searches tighter
combinations, hunting durable high win-rate (target 70-85%) without look-ahead.

Regime (no external index needed): build an equal-weight universe index from mean daily
returns, take its 200DMA. A day is REGIME-UP if the index sits above its own 200DMA.
Each stock-day inherits that day's regime; "gated" setups only fire on regime-up days.

Honest framing printed at the end: a high win-rate on a tiny N, or with a brutal worst-10%,
is not tradeable. We report N, win%, median, and worst-10% so win-rate isn't read alone.

Run:   python _scripts/backtest_regime.py
Env:   DATABASE_URL ; RG_FWD=60 (forward horizon, td) ; RG_MIN_N=1500 (min signals to rank)
       RG_MIN_HISTORY=220 ; RG_BREADTH ignored (index-based regime)
"""
import os, sys, warnings
import numpy as np
import pandas as pd
import psycopg2

warnings.filterwarnings("ignore")
URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
if not URL:
    sys.exit("DATABASE_URL not set")
FWD = int(os.environ.get("RG_FWD", "60"))
MIN_N = int(os.environ.get("RG_MIN_N", "1500"))
MIN_HISTORY = int(os.environ.get("RG_MIN_HISTORY", "220"))


def ema(a, span):
    return pd.Series(a).ewm(span=span, adjust=False).mean().to_numpy()

def rsi(c, period=14):
    d = np.diff(c, prepend=c[0])
    up = np.clip(d, 0, None); dn = np.clip(-d, 0, None)
    ru = pd.Series(up).ewm(alpha=1/period, adjust=False).mean().to_numpy()
    rd = pd.Series(dn).ewm(alpha=1/period, adjust=False).mean().to_numpy()
    rs = np.divide(ru, rd, out=np.full_like(ru, np.nan), where=rd != 0)
    return 100 - 100 / (1 + rs)


def per_symbol(df):
    c = df["close"].to_numpy(float).copy(); h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float); v = df["volume"].to_numpy(float)
    n = len(c)
    c[c <= 0] = np.nan                       # kill zero/neg closes (the divide-by-zero source)
    prev = np.roll(c, 1); prev[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev), np.abs(l - prev)))
    e200 = ema(c, 200); e50 = ema(c, 50)
    nr7 = np.zeros(n, bool); vr7 = np.zeros(n, bool)
    for i in range(6, n):
        w = tr[i-6:i+1]; nr7[i] = tr[i] == w.min(); vr7[i] = tr[i] == w.max()
    va = pd.Series(v).rolling(20).mean().shift(1).to_numpy()
    vr = np.divide(v, va, out=np.ones_like(v), where=(va > 0))
    mom6 = np.full(n, np.nan)
    if n > 126: mom6[126:] = (c[126:] / c[:-126] - 1) * 100
    roll_hi = pd.Series(h).rolling(252, min_periods=60).max().to_numpy()
    near = np.divide(roll_hi - c, roll_hi, out=np.full(n, np.nan), where=roll_hi > 0) * 100
    fwd = np.full(n, np.nan)
    if n > FWD:
        fwd[:-FWD] = (c[FWD:] / c[:-FWD] - 1) * 100
    ret1 = np.full(n, np.nan); ret1[1:] = c[1:] / c[:-1] - 1
    out = pd.DataFrame({
        "date": df["date"].values, "ret1": ret1,
        "above200": c > e200, "above50": c > e50, "nr7": nr7, "vr7": vr7,
        "vol_exp": vr >= 1.5, "vol2": vr >= 2.0,
        "mom15": mom6 >= 15, "mom25": mom6 >= 25,
        "rsi": rsi(c), "near5": near <= 5, "near3": near <= 3, f"fwd": fwd,
    })
    out["eligible"] = np.arange(n) >= MIN_HISTORY
    return out


def main():
    conn = psycopg2.connect(URL)
    cur = conn.cursor()
    cur.execute("SELECT symbol, date, open, high, low, close, volume FROM price_candles ORDER BY symbol, date")
    df = pd.DataFrame(cur.fetchall(), columns=["symbol","date","open","high","low","close","volume"])
    conn.close()
    print(f"  {len(df):,} candle rows / {df['symbol'].nunique():,} symbols  (fwd={FWD}td)")

    parts = []
    for sym, g in df.groupby("symbol", sort=False):
        if len(g) < MIN_HISTORY + FWD:
            continue
        s = per_symbol(g.reset_index(drop=True)); s["symbol"] = sym
        parts.append(s)
    A = pd.concat(parts, ignore_index=True)
    A["date"] = pd.to_datetime(A["date"]); A["year"] = A["date"].dt.year

    # ── market regime: equal-weight index > its own 200DMA ──
    breadth = A.groupby("date")["above200"].mean()
    idx_ret = A.groupby("date")["ret1"].mean()
    idx = (1 + idx_ret.fillna(0)).cumprod()
    idx_ma = idx.rolling(200, min_periods=120).mean()
    regime_up = (idx > idx_ma)
    A = A.merge(regime_up.rename("regime_up"), left_on="date", right_index=True, how="left")
    up_days = regime_up.mean()
    print(f"  regime: {up_days*100:.0f}% of days are uptrend (index>200DMA); "
          f"avg breadth {breadth.mean()*100:.0f}%\n")

    E = A[A["eligible"] & A["fwd"].notna()].copy()
    base = E["fwd"]
    b_win = (base > 0).mean() * 100; b_med = base.median()
    print(f"BASELINE (all eligible days)   N={len(E):,}  win={b_win:.1f}%  med={b_med:.2f}%")
    print(f"BASELINE | regime-UP only      N={(E['regime_up']).sum():,}  "
          f"win={(E.loc[E['regime_up'],'fwd']>0).mean()*100:.1f}%  "
          f"med={E.loc[E['regime_up'],'fwd'].median():.2f}%\n")

    # ── candidate setups (tightening filters) ──
    setups = {
        "near5+vol_exp+above200":            E.near5 & E.vol_exp & E.above200,
        "near3+vol_exp+above200":            E.near3 & E.vol_exp & E.above200,
        "near3+vol2+above200":               E.near3 & E.vol2 & E.above200,
        "near3+vol2+above200+mom15":         E.near3 & E.vol2 & E.above200 & E.mom15,
        "near3+vol2+above200+mom25":         E.near3 & E.vol2 & E.above200 & E.mom25,
        "near3+vol_exp+above200+above50+mom15": E.near3 & E.vol_exp & E.above200 & E.above50 & E.mom15,
        "nr7+vol_exp+above200+near3":        E.nr7 & E.vol_exp & E.above200 & E.near3,
        "vr7+vol2+above200+near3":           E.vr7 & E.vol2 & E.above200 & E.near3,
        "near3+vol2+above200+rsi55-75":      E.near3 & E.vol2 & E.above200 & E.rsi.between(55,75),
        "near3+vol_exp+above200+mom25+rsi50-72": E.near3 & E.vol_exp & E.above200 & E.mom25 & E.rsi.between(50,72),
    }

    print(f"{'SETUP':46} {'mode':10} {'N':>8} {'win%':>7} {'med%':>7} {'wrst10':>7} {'yrsEDGE+':>8}")
    print("-"*100)
    rows = []
    for name, mask in setups.items():
        for mode, m in (("all", mask), ("regime-UP", mask & E["regime_up"])):
            sub = E[m]; n = len(sub)
            if n < 50:
                continue
            win = (sub["fwd"] > 0).mean()*100; med = sub["fwd"].median()
            wrst = sub["fwd"].quantile(0.10)
            # per-year EDGE+ : year win% beats baseline win% by >5pts on N>=80
            yrs = 0
            for y, gy in sub.groupby("year"):
                if len(gy) >= 80 and (gy["fwd"]>0).mean()*100 > b_win + 5:
                    yrs += 1
            rows.append((name, mode, n, win, med, wrst, yrs))
            mark = "  <== TARGET" if (70 <= win <= 90 and n >= MIN_N and mode=="regime-UP") else ""
            print(f"{name:46} {mode:10} {n:>8,} {win:>6.1f}% {med:>6.2f}% {wrst:>6.1f}% {yrs:>7}{mark}")
    print("-"*100)
    # best regime-gated by win% with tradeable N
    cand = [r for r in rows if r[1]=="regime-UP" and r[2] >= MIN_N]
    cand.sort(key=lambda r: r[3], reverse=True)
    print(f"\nTOP regime-gated setups by win% (N >= {MIN_N}):")
    for r in cand[:5]:
        print(f"  {r[3]:.1f}% win | med {r[4]:.2f}% | worst10 {r[5]:.1f}% | N={r[2]:,} | EDGE+ yrs {r[6]} | {r[0]}")
    print("\nRead honestly: a high win% on a tiny N, or with a deep worst-10%, is not tradeable.")
    print("A durable winner clears baseline win% by a wide margin, on a healthy N, EDGE+ in many years.")


if __name__ == "__main__":
    main()
