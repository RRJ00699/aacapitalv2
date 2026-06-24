#!/usr/bin/env python3
"""
backtest_screener.py — does the technical screener actually predict anything?

Walks 5 years of price_candles, recomputes the SAME signals generate_signals.py uses
(EMA200/50, NR7, volume expansion, momentum, RSI, near-52w-high), and for every day a
given SETUP fires, measures forward returns at +5/+20/+60 trading days. Then compares
each setup's win-rate and median forward return against the BASELINE (the average
forward return of all stock-days in the same universe).

A setup only has an "edge" if it beats baseline by a meaningful margin on enough samples.
This is the honest gate before any combo gets labelled "profitable" in the UI.

Run:   python _scripts/backtest_screener.py
Env:   DATABASE_URL (or NEON_DATABASE_URL)
Opts:  BT_MIN_HISTORY=220   minimum candles before a symbol is eligible
       BT_HOLD="5,20,60"    forward horizons in trading days
"""
import os, sys
import numpy as np
import pandas as pd
import psycopg2

URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
if not URL:
    sys.exit("DATABASE_URL not set")

MIN_HISTORY = int(os.environ.get("BT_MIN_HISTORY", "220"))
HOLDS = [int(x) for x in os.environ.get("BT_HOLD", "5,20,60").split(",")]


def ema(arr, period):
    return pd.Series(arr).ewm(span=period, adjust=False).mean().to_numpy()


def rsi(closes, period=14):
    d = np.diff(closes, prepend=closes[0])
    up = np.where(d > 0, d, 0.0)
    dn = np.where(d < 0, -d, 0.0)
    ru = pd.Series(up).ewm(alpha=1/period, adjust=False).mean().to_numpy()
    rd = pd.Series(dn).ewm(alpha=1/period, adjust=False).mean().to_numpy()
    rs = np.divide(ru, rd, out=np.full_like(ru, np.nan), where=rd != 0)
    return 100 - 100 / (1 + rs)


def per_symbol_signals(df):
    """df: one symbol, sorted by date asc. Returns df with signal columns + forward returns."""
    c = df["close"].to_numpy(dtype=float)
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    v = df["volume"].to_numpy(dtype=float)
    n = len(c)

    # true range
    prev_c = np.roll(c, 1); prev_c[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))

    ema200 = ema(c, 200)
    ema50 = ema(c, 50)
    above200 = c > ema200

    # NR7: today's TR is the smallest of the last 7
    nr7 = np.zeros(n, dtype=bool)
    for i in range(6, n):
        nr7[i] = tr[i] == tr[i-6:i+1].min()

    # VR7: today's TR is the largest of the last 7 (range expansion / breakout)
    vr7 = np.zeros(n, dtype=bool)
    for i in range(6, n):
        vr7[i] = tr[i] == tr[i-6:i+1].max()

    # volume expansion vs trailing 20d avg
    vol_avg20 = pd.Series(v).rolling(20).mean().shift(1).to_numpy()
    vol_ratio = np.divide(v, vol_avg20, out=np.ones_like(v), where=(vol_avg20 > 0))
    vol_exp = vol_ratio >= 1.5

    # momentum 6m (~126 td)
    mom6 = np.full(n, np.nan)
    if n > 126:
        mom6[126:] = (c[126:] / c[:-126] - 1) * 100

    rsi14 = rsi(c)

    # 52w high proximity
    roll_hi = pd.Series(h).rolling(252, min_periods=60).max().to_numpy()
    near_hi = (roll_hi - c) / roll_hi * 100 <= 5

    out = pd.DataFrame({
        "date": df["date"].values, "close": c,
        "above200": above200, "nr7": nr7, "vr7": vr7,
        "vol_exp": vol_exp, "mom6": mom6, "rsi": rsi14, "near_hi": near_hi,
    })
    # forward returns
    for hd in HOLDS:
        fwd = np.full(n, np.nan)
        if n > hd:
            fwd[:-hd] = (c[hd:] / c[:-hd] - 1) * 100
        out[f"fwd{hd}"] = fwd
    # only rows with enough history to have valid ema200 + a forward window
    out["eligible"] = np.arange(n) >= MIN_HISTORY
    return out


# all candidate setups (the first pass tested these)
SETUPS = {
    "buyzone_high (above200+mom>=15+nr7)": lambda r: r.above200 and r.mom6 >= 15 and r.nr7,
    "nr7 + above200":                      lambda r: r.nr7 and r.above200,
    "nr7 + vol_exp + above200":            lambda r: r.nr7 and r.vol_exp and r.above200,
    "vr7 breakout + above200":             lambda r: r.vr7 and r.above200,
    "vr7 + vol_exp + above200":            lambda r: r.vr7 and r.vol_exp and r.above200,
    "nr7 + vol_exp + above200 + rsi45-65": lambda r: r.nr7 and r.vol_exp and r.above200 and 45 <= r.rsi <= 65,
    "near_52w_high + vol_exp + above200":  lambda r: r.near_hi and r.vol_exp and r.above200,
}

# the two combos that beat baseline in pass 1 — get the deep (downside + per-year) treatment
WINNERS = {
    "near_52w_high + vol_exp + above200": lambda r: r.near_hi and r.vol_exp and r.above200,
    "nr7 + vol_exp + above200":           lambda r: r.nr7 and r.vol_exp and r.above200,
}


def main():
    print(f"Loading price_candles … (min history {MIN_HISTORY}, horizons {HOLDS})")
    conn = psycopg2.connect(URL)
    df = pd.read_sql(
        "SELECT symbol, date, open, high, low, close, volume FROM price_candles ORDER BY symbol, date",
        conn,
    )
    conn.close()
    print(f"  {len(df):,} candle rows across {df['symbol'].nunique():,} symbols")

    parts = []
    for sym, g in df.groupby("symbol", sort=False):
        if len(g) < MIN_HISTORY + max(HOLDS):
            continue
        s = per_symbol_signals(g.reset_index(drop=True))
        s = s[s["eligible"]]
        parts.append(s)
    if not parts:
        sys.exit("Not enough history. Did the 5-year backfill run?")
    allsig = pd.concat(parts, ignore_index=True)
    print(f"  {len(allsig):,} eligible stock-days evaluated\n")

    # baseline = average forward return across all eligible stock-days
    print("=" * 92)
    print(f"{'SETUP':42s} {'N':>7s} " + " ".join(f"{'win'+str(h):>7s} {'med'+str(h):>7s}" for h in HOLDS))
    print("-" * 92)

    def line(name, sub):
        n = len(sub)
        cells = []
        for h in HOLDS:
            col = sub[f"fwd{h}"].dropna()
            win = (col > 0).mean() * 100 if len(col) else float("nan")
            med = col.median() if len(col) else float("nan")
            cells.append(f"{win:6.1f}% {med:6.2f}%")
        print(f"{name:42s} {n:7,d} " + " ".join(cells))

    line("BASELINE (all eligible days)", allsig)
    print("-" * 92)
    for name, fn in SETUPS.items():
        mask = allsig.apply(lambda r: bool(fn(r)) if pd.notna(r.rsi) else False, axis=1)
        sub = allsig[mask]
        if len(sub) < 30:
            print(f"{name:42s} {len(sub):7,d}   (too few signals to trust)")
            continue
        line(name, sub)
    print("=" * 92)

    # ── DEEP DIVE on the winners: downside + per-year, at the 60d horizon ──
    base60 = allsig["fwd60"].dropna()
    base_win = (base60 > 0).mean() * 100
    base_med = base60.median()
    base_p10 = base60.quantile(0.10)
    base_lose10 = (base60 < -10).mean() * 100
    allsig["year"] = pd.to_datetime(allsig["date"]).dt.year

    for name, fn in WINNERS.items():
        mask = allsig.apply(lambda r: bool(fn(r)) if pd.notna(r.rsi) else False, axis=1)
        sub = allsig[mask]
        print(f"\n{'#'*92}\n# DEEP DIVE: {name}   (60-day horizon)\n{'#'*92}")
        print(f"{'':18s} {'N':>8s} {'win%':>8s} {'median':>9s} {'worst10%':>10s} {'lost>10%':>10s}")
        c = sub['fwd60'].dropna()
        print(f"{'OVERALL':18s} {len(c):8,d} {(c>0).mean()*100:7.1f}% {c.median():8.2f}% "
              f"{c.quantile(0.10):9.2f}% {(c<-10).mean()*100:9.1f}%")
        print(f"{'BASELINE':18s} {len(base60):8,d} {base_win:7.1f}% {base_med:8.2f}% "
              f"{base_p10:9.2f}% {base_lose10:9.1f}%")
        print("  " + "-"*88)
        for yr in sorted(sub['year'].unique()):
            cy = sub[sub['year']==yr]['fwd60'].dropna()
            if len(cy) < 20:
                print(f"  {yr}             {len(cy):8,d}   (too few)")
                continue
            edge = (cy>0).mean()*100 - base_win
            print(f"  {yr:<16d} {len(cy):8,d} {(cy>0).mean()*100:7.1f}% {cy.median():8.2f}% "
                  f"{cy.quantile(0.10):9.2f}% {(cy<-10).mean()*100:9.1f}%   "
                  f"{'EDGE+' if edge>3 else 'flat ' if edge>-3 else 'WORSE'}")

    print("\nRead it like this: a setup has an EDGE only if its win-rate AND median forward")
    print("return clear the BASELINE row by a real margin, on a healthy N. If a combo barely")
    print("beats baseline, it's noise dressed up as signal — don't ship it as 'profitable'.")


if __name__ == "__main__":
    main()
