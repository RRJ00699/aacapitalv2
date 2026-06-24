#!/usr/bin/env python3
"""
momentum_backtest.py — does CROSS-SECTIONAL relative strength have a durable edge?

Different question from backtest_screener.py (which tested chart patterns and found them
2023-only). Here: at each month-end, rank the WHOLE universe by trailing return, buy the
top decile, hold forward, and compare to the universe average that month. Then break it
down PER YEAR — the only test that matters. A real edge is EDGE+ in >=3 of 5 years.

Pure price momentum first (no quality gate) — clean, no look-ahead bias. If this survives,
we test adding a quality / MF-holding gate next. If it's 2023-only too, relative strength
has no durable edge here and we stop.

Run:  python _scripts/momentum_backtest.py
Env:  DATABASE_URL ; MOM_LOOKBACK=126 (trading days ~6m) ; MOM_TOPPCT=10 (top decile)
      MOM_FWD=21,63,126 (forward horizons) ; MOM_SKIP=21 (skip most-recent month, std practice)
"""
import os, sys
import numpy as np
import pandas as pd
import psycopg2

URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
if not URL:
    sys.exit("DATABASE_URL not set")

LOOKBACK = int(os.environ.get("MOM_LOOKBACK", "126"))   # ~6 months
SKIP     = int(os.environ.get("MOM_SKIP", "21"))        # skip last ~1m (momentum convention)
TOPPCT   = float(os.environ.get("MOM_TOPPCT", "10"))    # top decile
FWDS     = [int(x) for x in os.environ.get("MOM_FWD", "21,63,126").split(",")]


def main():
    print(f"Loading price_candles … lookback={LOOKBACK}d skip={SKIP}d top={TOPPCT}% fwd={FWDS}")
    conn = psycopg2.connect(URL)
    df = pd.read_sql("SELECT symbol, date, close FROM price_candles ORDER BY symbol, date", conn)
    conn.close()
    df["date"] = pd.to_datetime(df["date"])
    print(f"  {len(df):,} rows / {df['symbol'].nunique():,} symbols")

    # pivot to a date x symbol close matrix, business-day aligned
    px = df.pivot_table(index="date", columns="symbol", values="close").sort_index()
    # month-end rebalance dates
    rebal = px.resample("ME").last().index
    rebal = [d for d in rebal if d in px.index or True]  # use nearest available below

    # helper: nearest index position on/just before a date
    idx = px.index
    def pos_on(d):
        i = idx.searchsorted(d, side="right") - 1
        return i if i >= 0 else None

    records = []
    for d in rebal:
        t = pos_on(d)
        if t is None or t - (LOOKBACK + SKIP) < 0:
            continue
        # need forward room for the longest horizon
        if t + max(FWDS) >= len(idx):
            continue
        row_now = px.iloc[t]
        row_back = px.iloc[t - (LOOKBACK + SKIP)]
        row_skip = px.iloc[t - SKIP]
        # momentum = return from (lookback+skip) ago to (skip) ago — classic 12-2 style
        mom = (row_skip / row_back - 1.0)
        valid = mom.dropna()
        valid = valid[np.isfinite(valid)]
        if len(valid) < 50:
            continue
        cutoff = np.percentile(valid, 100 - TOPPCT)
        winners = valid[valid >= cutoff].index
        # forward returns from now (t) for winners and for the whole valid universe
        for hd in FWDS:
            fut = px.iloc[t + hd]
            fwd_all = (fut[valid.index] / row_now[valid.index] - 1.0) * 100
            fwd_all = fwd_all.replace([np.inf, -np.inf], np.nan).dropna()
            fwd_win = (fut[winners] / row_now[winners] - 1.0) * 100
            fwd_win = fwd_win.replace([np.inf, -np.inf], np.nan).dropna()
            if len(fwd_win) == 0 or len(fwd_all) == 0:
                continue
            records.append({
                "date": d, "year": d.year, "hd": hd,
                "win_ret": fwd_win.values, "all_ret": fwd_all.values,
            })

    if not records:
        sys.exit("No rebalance windows produced — check history depth.")

    # aggregate per horizon, with per-year breakdown
    for hd in FWDS:
        rs = [r for r in records if r["hd"] == hd]
        win = np.concatenate([r["win_ret"] for r in rs])
        alls = np.concatenate([r["all_ret"] for r in rs])
        print("\n" + "=" * 78)
        print(f"FORWARD {hd} trading days  (~{round(hd/21)}m)   rebalances={len(rs)}")
        print("=" * 78)
        print(f"{'':14s} {'N':>9s} {'win%':>8s} {'mean':>8s} {'median':>8s} {'worst10%':>9s}")
        def stat(label, a, base_win=None):
            w = (a > 0).mean() * 100
            tag = ""
            if base_win is not None:
                e = w - base_win
                tag = "  EDGE+" if e > 3 else "  flat" if e > -3 else "  WORSE"
            print(f"{label:14s} {len(a):9,d} {w:7.1f}% {a.mean():7.2f}% {np.median(a):7.2f}% {np.percentile(a,10):8.2f}%{tag}")
        bw = (alls > 0).mean() * 100
        stat("UNIVERSE", alls)
        stat("TOP-MOM", win, bw)
        print("  " + "-" * 72)
        for yr in sorted({r["year"] for r in rs}):
            wy = np.concatenate([r["win_ret"] for r in rs if r["year"] == yr])
            ay = np.concatenate([r["all_ret"] for r in rs if r["year"] == yr])
            if len(wy) < 30:
                print(f"  {yr}: too few"); continue
            byw = (ay > 0).mean() * 100
            stat(f"  {yr} top", wy, byw)
    print("\n" + "=" * 78)
    print("Verdict rule: TOP-MOM must beat UNIVERSE win% by >3pts AND show EDGE+ in >=3 of")
    print("5 years, with a tolerable worst10%. One-year wonders don't ship.")


if __name__ == "__main__":
    main()
