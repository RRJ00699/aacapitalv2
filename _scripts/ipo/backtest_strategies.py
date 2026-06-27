#!/usr/bin/env python3
"""
backtest_strategies.py  —  AACapital: does ANY decidable post-listing rule make money?

Tests several entry rules that are ALL decidable at entry time (no lookahead) and exits at a
fixed horizon, net of round-trip costs. The point is to stop arguing and let the full 400-IPO
sample rank the strategies — buy-into-weakness vs buy-into-strength, head to head.

Trade return between two horizons uses exact prices (issue x (1+ret/100)):
    leg(r_from, r_to) = ((1 + r_to/100) / (1 + r_from/100) - 1) * 100
Entry "at issue" = r_from 0.  All return_* are percent vs issue.

Metrics per strategy: N, win%, avg%, median%, profit factor, worst, best, and avg/σ (a crude
Sharpe). Costs applied per trade (--cost-pct, round trip). Research only — not buy calls.

Usage:
  python _scripts/ipo/backtest_strategies.py
  python _scripts/ipo/backtest_strategies.py --min-size-cr 200 --cost-pct 0.6 --qib 2.0
"""
import os, sys, argparse, statistics

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

def leg(r_from, r_to):
    a, b = num(r_from), num(r_to)
    if a is None or b is None: return None
    denom = 1 + a / 100.0
    if abs(denom) < 1e-9: return None
    return ((1 + b / 100.0) / denom - 1) * 100.0

def report(name, rets, cost):
    rets = [r - cost for r in rets if r is not None]
    if not rets:
        print(f"  {name:46s}  n=0"); return None
    n = len(rets)
    wins = [r for r in rets if r > 0]; losses = [r for r in rets if r <= 0]
    avg = statistics.mean(rets); med = statistics.median(rets)
    pf = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else float("inf")
    sd = statistics.pstdev(rets) if n > 1 else 0.0
    shp = (avg / sd) if sd else float("nan")
    print(f"  {name:46s}  n={n:4d}  win {100*len(wins)/n:4.0f}%  "
          f"avg {avg:+6.1f}%  med {med:+6.1f}%  PF {pf:4.2f}  "
          f"σ {sd:4.0f}  avg/σ {shp:+.2f}  [{min(rets):+.0f}..{max(rets):+.0f}]")
    return avg

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-size-cr", type=float, default=200.0)
    ap.add_argument("--cost-pct", type=float, default=0.6, help="round-trip cost+slippage per trade")
    ap.add_argument("--qib", type=float, default=2.0, help="QIB subscription threshold for 'strong'")
    args = ap.parse_args()

    conn = connect(); cur = conn.cursor()
    cur.execute("""SELECT column_name FROM information_schema.columns WHERE table_name='ipo_intelligence'""")
    cols = {r[0] for r in cur.fetchall()}
    size = "COALESCE(issue_size_cr)" if "issue_size_cr" in cols else "NULL"
    sme = "is_sme" if "is_sme" in cols else "FALSE"
    qib = "qib_subscription_x" if "qib_subscription_x" in cols else "NULL"
    cur.execute(f"""
        SELECT company_name, return_listing_open, return_day7, return_day30, return_day90,
               max_upside_30d, max_drawdown_30d, {size} sz, {sme} sme, {qib} qib
        FROM ipo_intelligence WHERE listing_date IS NOT NULL""")
    rows = [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
    conn.close()

    U = [r for r in rows if r["sme"] is not True and (num(r["sz"]) or 0) >= args.min_size_cr]
    C = args.cost_pct
    Q = args.qib
    def q_ok(r): v = num(r["qib"]); return v is not None and v >= Q
    def disc(r): v = num(r["return_listing_open"]); return v is not None and v <= 0
    def prem(r): v = num(r["return_listing_open"]); return v is not None and v > 0
    def reclaimed7(r): v = num(r["return_day7"]); return v is not None and v >= 0
    def improving(r):
        o, s = num(r["return_listing_open"]), num(r["return_day7"]); return o is not None and s is not None and s > o

    print("=" * 100)
    print(f"AACAPITAL STRATEGY SEARCH — mainboard, issue>={args.min_size_cr:.0f}cr, "
          f"n={len(U)}, cost {C}%/trade, QIB strong>={Q}x")
    print("=" * 100)
    print("(every rule is decidable at entry — no lookahead. metrics are NET of cost.)\n")

    print("— BASELINES —")
    report("A  buy LISTING OPEN → sell d30 (all)",            [leg(r["return_listing_open"], r["return_day30"]) for r in U], C)
    report("A90 buy LISTING OPEN → sell d90 (all)",           [leg(r["return_listing_open"], r["return_day90"]) for r in U], C)

    print("\n— BUY INTO WEAKNESS (the family we already doubted) —")
    report("W1 buy open if DISCOUNT → sell d30",              [leg(r["return_listing_open"], r["return_day30"]) for r in U if disc(r)], C)
    report("W2 buy open if DISCOUNT + QIB>=thr → sell d30",   [leg(r["return_listing_open"], r["return_day30"]) for r in U if disc(r) and q_ok(r)], C)
    report("W3 buy open if DISCOUNT + QIB>=thr → sell d90",   [leg(r["return_listing_open"], r["return_day90"]) for r in U if disc(r) and q_ok(r)], C)

    print("\n— BUY INTO STRENGTH / CONFIRMATION (Strategy C family, untested) —")
    report("S1 buy d7 if RECLAIMED issue → sell d30",         [leg(r["return_day7"], r["return_day30"]) for r in U if reclaimed7(r)], C)
    report("S2 buy d7 if RECLAIMED + QIB>=thr → sell d30",    [leg(r["return_day7"], r["return_day30"]) for r in U if reclaimed7(r) and q_ok(r)], C)
    report("S3 buy d7 if RECLAIMED → sell d90",               [leg(r["return_day7"], r["return_day90"]) for r in U if reclaimed7(r)], C)
    report("S4 buy d7 if RECLAIMED + QIB>=thr → sell d90",    [leg(r["return_day7"], r["return_day90"]) for r in U if reclaimed7(r) and q_ok(r)], C)
    report("S5 buy d7 if IMPROVING vs open → sell d30",       [leg(r["return_day7"], r["return_day30"]) for r in U if improving(r)], C)

    print("\n— PREMIUM / MOMENTUM (did strong listers keep going?) —")
    report("P1 buy open if PREMIUM listing → sell d30",       [leg(r["return_listing_open"], r["return_day30"]) for r in U if prem(r)], C)
    report("P2 buy d7 if PREMIUM + still up@d7 → sell d30",   [leg(r["return_day7"], r["return_day30"]) for r in U if prem(r) and reclaimed7(r)], C)

    print("\nReading: a rule beats the others only if win% AND avg AND PF AND avg/σ agree, on a")
    print("reasonable N. One strategy looking great on n=8 is noise. Costs are already netted.")

if __name__ == "__main__":
    main()
