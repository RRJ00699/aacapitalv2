#!/usr/bin/env python3
"""
backtest_regime_split.py  —  is the edge real, or just one bull market?

Splits the two strategies that beat noise in backtest_strategies.py by LISTING YEAR:
  W2 = buy discount open + QIB>=2x → sell d30
  S3 = buy d7 if reclaimed issue   → sell d90
If +4% avg is really one or two hot years and ~0 since, it's regime, not edge — and you should
NOT trade it. A real edge shows up positive across most years, not all of it in 2021.

Usage:
  python _scripts/ipo/backtest_regime_split.py
  python _scripts/ipo/backtest_regime_split.py --cost-pct 0.6 --qib 2.0
"""
import os, sys, argparse, statistics
from collections import defaultdict

def num(v):
    try: return None if v is None else float(v)
    except (TypeError, ValueError): return None

def connect():
    url = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not url: sys.exit("Set DATABASE_URL or NEON_DATABASE_URL.")
    try:
        import psycopg2; return psycopg2.connect(url)
    except ImportError:
        import psycopg; return psycopg.connect(url)

def leg(a, b):
    a, b = num(a), num(b)
    if a is None or b is None: return None
    d = 1 + a / 100.0
    return None if abs(d) < 1e-9 else ((1 + b / 100.0) / d - 1) * 100.0

def stats(rets, cost):
    rets = [r - cost for r in rets if r is not None]
    if not rets: return None
    wins = [r for r in rets if r > 0]; losses = [r for r in rets if r <= 0]
    pf = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else float("inf")
    return len(rets), 100 * len(wins) / len(rets), statistics.mean(rets), statistics.median(rets), pf

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-size-cr", type=float, default=200.0)
    ap.add_argument("--cost-pct", type=float, default=0.6)
    ap.add_argument("--qib", type=float, default=2.0)
    args = ap.parse_args()

    conn = connect(); cur = conn.cursor()
    cur.execute("""SELECT column_name FROM information_schema.columns WHERE table_name='ipo_intelligence'""")
    cols = {r[0] for r in cur.fetchall()}
    sme = "is_sme" if "is_sme" in cols else "FALSE"
    qib = "qib_subscription_x" if "qib_subscription_x" in cols else "NULL"
    cur.execute(f"""
        SELECT EXTRACT(YEAR FROM listing_date)::int AS yr,
               return_listing_open, return_day7, return_day30, return_day90,
               COALESCE(issue_size_cr) AS sz, {sme} AS sme, {qib} AS qib
        FROM ipo_intelligence WHERE listing_date IS NOT NULL""")
    rows = [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
    conn.close()

    U = [r for r in rows if r["sme"] is not True and (num(r["sz"]) or 0) >= args.min_size_cr]
    C, Q = args.cost_pct, args.qib

    def w2(r):
        o = num(r["return_listing_open"]); q = num(r["qib"])
        return leg(r["return_listing_open"], r["return_day30"]) if (o is not None and o <= 0 and q is not None and q >= Q) else None
    def s3(r):
        d7 = num(r["return_day7"])
        return leg(r["return_day7"], r["return_day90"]) if (d7 is not None and d7 >= 0) else None

    for name, fn in [("W2  buy discount+QIB>=%.0fx → d30" % Q, w2),
                     ("S3  buy d7 reclaimed → d90", s3)]:
        by_year = defaultdict(list)
        for r in U:
            v = fn(r)
            if v is not None and r["yr"]:
                by_year[r["yr"]].append(v)
        print("=" * 72)
        print(name + f"   (cost {C}%/trade, net)")
        print("=" * 72)
        print(f"  {'year':>6s} {'n':>5s} {'win%':>6s} {'avg%':>8s} {'med%':>8s} {'PF':>6s}")
        allr = []
        for yr in sorted(by_year):
            s = stats(by_year[yr], C); allr += [x - C for x in by_year[yr]]
            if s: print(f"  {yr:>6d} {s[0]:>5d} {s[1]:>5.0f}% {s[2]:>+7.1f}% {s[3]:>+7.1f}% {s[4]:>6.2f}")
        if allr:
            wins = [x for x in allr if x > 0]; los = [x for x in allr if x <= 0]
            pf = (sum(wins)/abs(sum(los))) if los and sum(los) else float("inf")
            print(f"  {'ALL':>6s} {len(allr):>5d} {100*len(wins)/len(allr):>5.0f}% "
                  f"{statistics.mean(allr):>+7.1f}% {statistics.median(allr):>+7.1f}% {pf:>6.2f}")
        pos_years = sum(1 for yr in by_year if (stats(by_year[yr], C) or [0,0,0])[2] > 0)
        print(f"  → positive in {pos_years}/{len(by_year)} years "
              f"({'looks regime-stable' if pos_years >= 0.6*len(by_year) else 'CONCENTRATED — likely regime, be careful'})\n")

if __name__ == "__main__":
    main()
