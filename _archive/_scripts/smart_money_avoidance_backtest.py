#!/usr/bin/env python3
"""
smart_money_avoidance_backtest.py — does INSTITUTIONAL DISTRIBUTION predict UNDERPERFORMANCE?

Unlike price patterns/momentum (both proven 2023-only mirages), this tests a fundamentally
different signal: stocks where FII+DII+MF holding ROSE the most quarter-over-quarter.
If "smart money accumulating" has a durable edge where price signals don't, it's the real spine.

Point-in-time honest:
  • signal = change in (fii_pct+dii_pct+mf_pct) vs the prior quarter, per stock
  • ENTRY is LAG_DAYS after quarter_date (shareholding is disclosed weeks late — entering at
    quarter_date would be look-ahead cheating). Default 45 days.
  • each quarter, rank the universe by accumulation; top quintile = "ACCUMULATED"
  • forward returns vs the whole universe that quarter, broken down PER YEAR + downside

CAVEAT printed at runtime: shareholding_history is usually only ~8 quarters deep (~2yr),
so this is SUGGESTIVE, not as conclusive as the 5-year price backtests. Read accordingly.

Run:  python _scripts/smart_money_backtest.py
Env:  DATABASE_URL ; SM_LAG=45 (disclosure lag, days) ; SM_TOPPCT=20 (top quintile)
      SM_FWD=63,126,252 (forward trading-day horizons)
"""
import os, sys, re
import numpy as np
import pandas as pd
import psycopg2

URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
if not URL:
    sys.exit("DATABASE_URL not set")

LAG    = int(os.environ.get("SM_LAG", "45"))
BOTPCT = float(os.environ.get("SM_BOTPCT", "20"))   # bottom quintile = heaviest selling
FWDS   = [int(x) for x in os.environ.get("SM_FWD", "63,126,252").split(",")]


def main():
    conn = psycopg2.connect(URL)
    sh = pd.read_sql("""
        SELECT nse_symbol, quarter,
               COALESCE(fii_pct,0)+COALESCE(dii_pct,0)+COALESCE(mf_pct,0) AS inst
        FROM shareholding_history
        WHERE quarter IS NOT NULL AND nse_symbol IS NOT NULL
    """, conn)
    px = pd.read_sql("SELECT symbol, date, close FROM price_candles ORDER BY symbol, date", conn)
    conn.close()

    QEND = {"Q1": (6, 30), "Q2": (9, 30), "Q3": (12, 31), "Q4": (3, 31)}
    def q_to_date(q):
        m = re.match(r"(\d{4})Q([1-4])", str(q).strip())
        if not m:
            return pd.NaT
        mo, day = QEND["Q" + m.group(2)]
        return pd.Timestamp(year=int(m.group(1)), month=mo, day=day)
    sh["quarter_date"] = sh["quarter"].apply(q_to_date)
    sh = sh.dropna(subset=["quarter_date"]).sort_values(["nse_symbol", "quarter_date"])
    px["date"] = pd.to_datetime(px["date"])
    qs = sorted(sh["quarter_date"].unique())
    print(f"shareholding: {len(sh):,} rows / {sh['nse_symbol'].nunique():,} symbols / "
          f"{len(qs)} quarters ({pd.Timestamp(qs[0]).date()} → {pd.Timestamp(qs[-1]).date()})")
    if len(qs) < 4:
        print("WARNING: very few quarters — results are weak/indicative only.")

    # per-symbol price arrays for fast forward lookups
    pxg = {s: g.reset_index(drop=True) for s, g in px.groupby("symbol", sort=False)}

    def fwd_return(sym, entry_date, horizon):
        g = pxg.get(sym)
        if g is None:
            return None
        i = g["date"].searchsorted(entry_date, side="left")
        if i >= len(g) or i + horizon >= len(g):
            return None
        p0 = g["close"].iloc[i]; p1 = g["close"].iloc[i + horizon]
        if not p0 or p0 <= 0:
            return None
        return (p1 / p0 - 1.0) * 100

    # compute per-quarter accumulation (delta vs prior quarter) per symbol
    sh = sh.sort_values(["nse_symbol", "quarter_date"])
    sh["prev_inst"] = sh.groupby("nse_symbol")["inst"].shift(1)
    sh["delta"] = sh["inst"] - sh["prev_inst"]
    sig = sh.dropna(subset=["delta"]).copy()
    # CRITICAL: 83% of rows have inst=0 (FII/DII/MF not captured) -> a column of zeros.
    # Ranking quintiles on that swept 76% of the universe into BOTH tails and made every
    # result identical/flat. Keep only rows with REAL institutional data AND a real move.
    before = len(sig)
    sig = sig[(sig["inst"] > 0) & (sig["prev_inst"] > 0) & (sig["delta"] != 0)].copy()
    print(f"signal rows with REAL institutional movement: {len(sig):,} "
          f"(filtered out {before-len(sig):,} zero/no-data rows)")

    records = []
    for qd in sorted(sig["quarter_date"].unique()):
        q = sig[sig["quarter_date"] == qd]
        if len(q) < 40:
            continue
        cut = np.percentile(q["delta"], BOTPCT)   # bottom quintile threshold
        entry_date = pd.Timestamp(qd) + pd.Timedelta(days=LAG)
        for hd in FWDS:
            dump, uni = [], []
            for _, r in q.iterrows():
                fr = fwd_return(r["nse_symbol"], entry_date, hd)
                if fr is None:
                    continue
                uni.append(fr)
                if r["delta"] <= cut:
                    dump.append(fr)
            if len(dump) >= 5 and len(uni) >= 20:
                records.append({"qd": pd.Timestamp(qd), "year": pd.Timestamp(qd).year,
                                "hd": hd, "dump": np.array(dump), "uni": np.array(uni)})

    if not records:
        sys.exit("No quarters produced signals — check shareholding depth / price alignment.")

    for hd in FWDS:
        rs = [r for r in records if r["hd"] == hd]
        if not rs:
            continue
        dump = np.concatenate([r["dump"] for r in rs])
        uni = np.concatenate([r["uni"] for r in rs])
        print("\n" + "=" * 80)
        print(f"FORWARD {hd} trading days (~{round(hd/21)}m)   quarters={len({r['qd'] for r in rs})}"
              f"   entry = quarter_date + {LAG}d (disclosure lag)")
        print("=" * 80)
        print(f"{'':16s} {'N':>8s} {'win%':>8s} {'mean':>8s} {'median':>8s} {'worst10%':>9s}")
        def stat(label, a, basew=None):
            w = (a > 0).mean() * 100
            tag = ""
            if basew is not None:
                e = w - basew   # NEGATIVE e = underperforms = the avoidance signal WORKS
                tag = "  AVOID+" if e < -3 else "  flat" if e < 3 else "  (outperforms?!)"
            print(f"{label:16s} {len(a):8,d} {w:7.1f}% {a.mean():7.2f}% {np.median(a):7.2f}% {np.percentile(a,10):8.2f}%{tag}")
        bw = (uni > 0).mean() * 100
        stat("UNIVERSE", uni)
        stat("DUMPED", dump, bw)
        print("  " + "-" * 74)
        for yr in sorted({r["year"] for r in rs}):
            dy = np.concatenate([r["dump"] for r in rs if r["year"] == yr])
            uy = np.concatenate([r["uni"] for r in rs if r["year"] == yr])
            if len(dy) < 15:
                print(f"  {yr}: too few"); continue
            stat(f"  {yr} dumped", dy, (uy > 0).mean() * 100)
    print("\n" + "=" * 80)
    print("Verdict (AVOIDANCE): DUMPED stocks should UNDERperform UNIVERSE by >3pts win%")
    print("(AVOID+ tag) across the years present. If DUMPED reliably lags, 'avoid what smart")
    print("money flees' is a durable RISK FILTER. 2025 is a thin/partial year — discount it.")


if __name__ == "__main__":
    main()
