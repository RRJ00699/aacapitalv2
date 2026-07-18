#!/usr/bin/env python3
"""
mf_accumulation_backtest.py — does ACCUMULATION by conviction MF funds predict forward returns?

This is the cleanest smart-money test in the project: mf_scheme_holdings has DATED,
point-in-time monthly holdings for 7 high-conviction active funds (Nippon/quant/Canara/PPFAS,
small/mid/flexi-cap), joined to nse_symbol, joinable to price_candles. No look-ahead, dense,
behavioral.

Signal per (stock, month): change in TOTAL portfolio weight held across all funds vs the
prior month the stock appeared. Two cross-sectional signals tested each month:
  • ADDED   = top quintile by weight increase (funds piling in)
  • NEW     = stock newly appearing in a fund's book this month (fresh conviction buy)
  • DROPPED = bottom quintile (funds cutting) -> tested for UNDER-performance (avoidance)

Entry is the month-end + a small lag (holdings are disclosed ~end of month, tradeable next
month). Forward returns vs the universe of all MF-held stocks that month, per YEAR, with
downside — same honest lens as every other backtest.

Run:  python _scripts/mf/mf_accumulation_backtest.py
Env:  DATABASE_URL ; MF_LAG_DAYS=10 ; MF_TOPPCT=20 ; MF_FWD=21,63,126 (fwd trading days)
      MF_MIN_DELTA=0.1 (min weight-pt move to count as a real add/drop)
"""
import os, sys
import numpy as np
import pandas as pd
import psycopg2

URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
if not URL:
    sys.exit("DATABASE_URL not set")

LAG    = int(os.environ.get("MF_LAG_DAYS", "10"))
TOPPCT = float(os.environ.get("MF_TOPPCT", "20"))
FWDS   = [int(x) for x in os.environ.get("MF_FWD", "21,63,126").split(",")]
MINDLT = float(os.environ.get("MF_MIN_DELTA", "0.1"))


def main():
    conn = psycopg2.connect(URL)
    # total weight per stock per month across ALL funds (a stock in 3 funds sums their weights)
    mf = pd.read_sql("""
        SELECT month, nse_symbol,
               SUM(COALESCE(portfolio_weight_pct,0)) AS wt,
               COUNT(DISTINCT scheme_name)           AS n_funds
        FROM mf_scheme_holdings
        WHERE nse_symbol IS NOT NULL AND nse_symbol <> ''
        GROUP BY month, nse_symbol
    """, conn)
    px = pd.read_sql("SELECT symbol, date, close FROM price_candles ORDER BY symbol, date", conn)
    conn.close()

    mf["month"] = pd.to_datetime(mf["month"])
    px["date"] = pd.to_datetime(px["date"])
    months = sorted(mf["month"].unique())
    print(f"MF holdings: {len(mf):,} stock-months / {mf['nse_symbol'].nunique():,} stocks / "
          f"{len(months)} months ({pd.Timestamp(months[0]).date()} .. {pd.Timestamp(months[-1]).date()})")

    # weight % in this file is a FRACTION (0.0259 = 2.59%); normalise to pct points for readability
    if mf["wt"].max() < 1.5:
        mf["wt"] = mf["wt"] * 100.0

    pxg = {s: g.reset_index(drop=True) for s, g in px.groupby("symbol", sort=False)}

    def fwd(sym, entry_date, h):
        g = pxg.get(sym)
        if g is None:
            return None
        i = g["date"].searchsorted(entry_date, side="left")
        if i >= len(g) or i + h >= len(g):
            return None
        p0 = g["close"].iloc[i]; p1 = g["close"].iloc[i + h]
        return (p1 / p0 - 1) * 100 if p0 and p0 > 0 else None

    # month-over-month weight change per stock
    mf = mf.sort_values(["nse_symbol", "month"])
    mf["prev_wt"] = mf.groupby("nse_symbol")["wt"].shift(1)
    mf["prev_month"] = mf.groupby("nse_symbol")["month"].shift(1)
    # only treat consecutive months as a real delta (gap = stock left & re-entered)
    mf["delta"] = mf["wt"] - mf["prev_wt"]
    mf["is_new"] = mf["prev_wt"].isna()

    recs = []
    for m in months[1:]:
        snap = mf[mf["month"] == m].copy()
        if len(snap) < 30:
            continue
        moved = snap[(snap["delta"].notna()) & (snap["delta"].abs() >= MINDLT)]
        if len(moved) < 20:
            continue
        add_cut  = np.percentile(moved["delta"], 100 - TOPPCT)
        drop_cut = np.percentile(moved["delta"], TOPPCT)
        entry = pd.Timestamp(m) + pd.Timedelta(days=LAG)
        for h in FWDS:
            uni, added, dropped, new = [], [], [], []
            for _, r in snap.iterrows():
                fr = fwd(r["nse_symbol"], entry, h)
                if fr is None:
                    continue
                uni.append(fr)
                if r["is_new"]:
                    new.append(fr)
                d = r["delta"]
                if pd.notna(d) and abs(d) >= MINDLT:
                    if d >= add_cut:  added.append(fr)
                    if d <= drop_cut: dropped.append(fr)
            if len(uni) >= 20:
                recs.append({"m": pd.Timestamp(m), "yr": pd.Timestamp(m).year, "h": h,
                             "uni": np.array(uni), "added": np.array(added),
                             "dropped": np.array(dropped), "new": np.array(new)})

    if not recs:
        sys.exit("No monthly signals produced — check holdings/price overlap.")

    def stat(label, a, basew=None, invert=False):
        if len(a) < 5:
            print(f"  {label:18s} {len(a):>6,d}      —        —      —      —"); return
        w = (a > 0).mean() * 100
        tag = ""
        if basew is not None:
            e = w - basew
            if invert:
                tag = "  AVOID+" if e < -3 else "  flat" if e < 3 else "  (outperf?!)"
            else:
                tag = "  EDGE+" if e > 3 else "  flat" if e > -3 else "  WORSE"
        print(f"  {label:18s} {len(a):>6,d} {w:6.1f}% {a.mean():7.2f}% "
              f"{np.median(a):7.2f}% {np.percentile(a,10):7.2f}%{tag}")

    for h in FWDS:
        rs = [r for r in recs if r["h"] == h]
        if not rs:
            continue
        uni = np.concatenate([r["uni"] for r in rs])
        print("\n" + "=" * 78)
        print(f"FORWARD {h} trading days (~{round(h/21)}m)   months={len({r['m'] for r in rs})}"
              f"   entry = month-end + {LAG}d")
        print("=" * 78)
        print(f"  {'bucket':18s} {'n':>6s} {'win%':>6s} {'mean':>7s} {'median':>7s} {'worst10':>7s}")
        bw = (uni > 0).mean() * 100
        stat("UNIVERSE (MF-held)", uni)
        stat("ADDED (top wt rise)", np.concatenate([r["added"] for r in rs]), bw)
        stat("NEW (fresh buy)",     np.concatenate([r["new"] for r in rs]), bw)
        stat("DROPPED (cutting)",   np.concatenate([r["dropped"] for r in rs]), bw, invert=True)
        print("  " + "-" * 72)
        for yr in sorted({r["yr"] for r in rs}):
            ay = np.concatenate([r["added"] for r in rs if r["yr"] == yr])
            uy = np.concatenate([r["uni"] for r in rs if r["yr"] == yr])
            if len(ay) >= 10:
                stat(f"  {yr} ADDED", ay, (uy > 0).mean() * 100)
        print("  " + "·" * 72)
        for yr in sorted({r["yr"] for r in rs}):
            ny = np.concatenate([r["new"] for r in rs if r["yr"] == yr])
            uy = np.concatenate([r["uni"] for r in rs if r["yr"] == yr])
            if len(ny) >= 10:
                stat(f"  {yr} NEW", ny, (uy > 0).mean() * 100)

    print("\n" + "=" * 78)
    print("READ: ADDED/NEW must beat UNIVERSE by >3pts win% with EDGE+ across years to be a")
    print("real buy signal. DROPPED should UNDERperform (AVOID+) to be a risk filter. These")
    print("are 7 small/mid/flexi funds — a conviction-manager lens, not all of institutional India.")


if __name__ == "__main__":
    main()
