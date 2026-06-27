#!/usr/bin/env python3
"""
backtest_recovery_classes.py  —  AACapital IPO Recovery Engine, Hypothesis 3.

Question (different from the dip-defense test): of mainboard IPOs that listed BELOW
issue price, what fraction RECLAIM the issue price within 7 / 30 days — i.e. "listing
below issue != failed IPO"?  Reports base rates AND the IPO names in each bucket.

DATA HONESTY: ipo_intelligence stores point-in-time returns (day7/day30/day90) and
max_upside_30d / max_drawdown_30d — NOT a full daily close series. So:
  • "reclaimed issue within 30d"  = max_upside_30d >= 0   (touched issue at some point)
  • "above issue at day7 close"   = return_day7  >= 0
  • "above issue at day30 close"  = return_day30 >= 0
  • "above issue at day90 close"  = return_day90 >= 0
Day-15 is not used (column largely unpopulated; run the returns backfill to add it).
All return_* columns are percent = (price/issue - 1) * 100.

Usage:
  python _scripts/ipo/backtest_recovery_classes.py
  python _scripts/ipo/backtest_recovery_classes.py --min-size-cr 200 --csv recovery.csv
  python _scripts/ipo/backtest_recovery_classes.py --discount-max 0   # how deep a discount counts
"""
import os, sys, csv, argparse

def num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None

def pct(a, b):
    return (100.0 * a / b) if b else 0.0

def connect():
    url = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not url:
        sys.exit("Set DATABASE_URL or NEON_DATABASE_URL.")
    try:
        import psycopg2
        return psycopg2.connect(url)
    except ImportError:
        import psycopg  # psycopg3 fallback
        return psycopg.connect(url)

def has_cols(cur):
    cur.execute("""SELECT column_name FROM information_schema.columns
                   WHERE table_name = 'ipo_intelligence'""")
    return {r[0] for r in cur.fetchall()}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-size-cr", type=float, default=200.0)
    ap.add_argument("--discount-max", type=float, default=0.0,
                    help="listing_open return must be <= this to count as 'listed at discount' (default 0)")
    ap.add_argument("--csv", default=None)
    args = ap.parse_args()

    conn = connect(); cur = conn.cursor()
    cols = has_cols(cur)

    size_pref = ["issue_size_cr", "issue_size", "issue_size_crores", "size_cr"]
    size_cols = [c for c in size_pref if c in cols]
    size_expr = ("COALESCE(" + ", ".join(size_cols) + ")") if size_cols else "NULL"
    sme_expr  = "is_sme" if "is_sme" in cols else "FALSE"
    qib_expr  = "qib_subscription_x" if "qib_subscription_x" in cols else "NULL"

    cur.execute(f"""
        SELECT company_name, nse_symbol, issue_price, listing_date,
               return_listing_open, return_day7, return_day30, return_day90,
               max_upside_30d, max_drawdown_30d,
               {size_expr} AS issue_size_cr, {sme_expr} AS is_sme, {qib_expr} AS qib_x
        FROM ipo_intelligence
        WHERE listing_date IS NOT NULL
        ORDER BY listing_date
    """)
    rows = [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
    conn.close()

    print("=" * 86)
    print("AACAPITAL IPO RECOVERY BACKTEST — Hypothesis 3 (listing below issue != failed IPO)")
    print("=" * 86)
    print(f"issue-size source: {', '.join(size_cols) if size_cols else 'NONE'} | "
          f"is_sme: {'yes' if 'is_sme' in cols else 'n/a→all mainboard'} | "
          f"QIB: {'yes' if 'qib_subscription_x' in cols else 'n/a'}")

    # universe: mainboard, >= size, with the key columns present
    def keep(r):
        sz = num(r["issue_size_cr"])
        if r["is_sme"] is True:                     return False
        if sz is None or sz < args.min_size_cr:     return False
        if num(r["return_listing_open"]) is None:   return False
        if num(r["max_upside_30d"]) is None:        return False
        return True

    univ = [r for r in rows if keep(r)]
    print(f"\nUniverse (mainboard, issue >= {args.min_size_cr:.0f}cr, key data present): {len(univ)}")

    # discount cohort
    disc = [r for r in univ if num(r["return_listing_open"]) <= args.discount_max]
    print(f"Listed at discount (listing_open <= {args.discount_max:+.0f}%): {len(disc)}  "
          f"({pct(len(disc), len(univ)):.0f}% of universe)")
    if not disc:
        print("No discount-listed IPOs under these filters."); return

    # recovery flags
    def f(r, k): return num(r[k])
    touched_30 = [r for r in disc if (f(r, "max_upside_30d") or -1) >= 0]
    above_7    = [r for r in disc if f(r, "return_day7")  is not None and f(r, "return_day7")  >= 0]
    above_30   = [r for r in disc if f(r, "return_day30") is not None and f(r, "return_day30") >= 0]
    above_90   = [r for r in disc if f(r, "return_day90") is not None and f(r, "return_day90") >= 0]
    never_30   = [r for r in disc if (f(r, "max_upside_30d") or -1) < 0]

    dds = [f(r, "max_drawdown_30d") for r in disc if f(r, "max_drawdown_30d") is not None]
    avg_dd = sum(dds) / len(dds) if dds else float("nan")

    print("\n" + "-" * 86)
    print("RECOVERY BASE RATES (of the discount cohort)")
    print("-" * 86)
    print(f"  Reclaimed issue at some point within 30d (max_upside>=0) : {len(touched_30)}/{len(disc)}  ({pct(len(touched_30),len(disc)):.0f}%)")
    print(f"  Closed >= issue at day 7                                 : {len(above_7)}/{len(disc)}  ({pct(len(above_7),len(disc)):.0f}%)")
    print(f"  Closed >= issue at day 30                                : {len(above_30)}/{len(disc)}  ({pct(len(above_30),len(disc)):.0f}%)")
    print(f"  Closed >= issue at day 90                                : {len(above_90)}/{len(disc)}  ({pct(len(above_90),len(disc)):.0f}%)")
    print(f"  Never reclaimed issue within 30d                         : {len(never_30)}/{len(disc)}  ({pct(len(never_30),len(disc)):.0f}%)  <- capital-at-risk")
    print(f"  Avg max drawdown vs issue (depth of the dip)             : {avg_dd:+.1f}%")

    # optional: Hypothesis 1 — strong QIB within the discount cohort
    if "qib_subscription_x" in cols:
        q = [(r, f(r, "qib_x")) for r in disc if f(r, "qib_x") is not None]
        strong = [r for r, v in q if v >= 2.0]
        weak   = [r for r, v in q if v < 2.0]
        def rec_rate(grp): 
            return pct(len([r for r in grp if (f(r,"max_upside_30d") or -1) >= 0]), len(grp)) if grp else float("nan")
        print("\n  Hypothesis 1 (QIB strength → recovery), 'reclaimed within 30d':")
        print(f"    QIB >= 2x : {rec_rate(strong):.0f}%  (n={len(strong)})")
        print(f"    QIB <  2x : {rec_rate(weak):.0f}%  (n={len(weak)})")

    def show(title, grp, key, reverse=True, limit=60):
        print("\n" + "-" * 86)
        print(f"{title}  (n={len(grp)})")
        print("-" * 86)
        print(f"  {'company':34s} {'sym':>11s} {'issue':>7s} {'open%':>7s} {'d7%':>7s} {'d30%':>7s} {'d90%':>7s} {'maxUp%':>7s} {'maxDD%':>7s}")
        g = sorted(grp, key=lambda r: (f(r, key) if f(r, key) is not None else -999), reverse=reverse)
        for r in g[:limit]:
            def s(k): 
                v = f(r, k); return f"{v:7.1f}" if v is not None else f"{'—':>7s}"
            iss = num(r["issue_price"]) or 0
            print(f"  {(r['company_name'] or '?')[:34]:34s} {(r['nse_symbol'] or ''):>11s} "
                  f"{iss:7.1f} {s('return_listing_open')} {s('return_day7')} {s('return_day30')} "
                  f"{s('return_day90')} {s('max_upside_30d')} {s('max_drawdown_30d')}")
        if len(grp) > limit:
            print(f"  ... ({len(grp)-limit} more — use --csv for the full list)")

    # the names the user asked for, in the buckets that matter
    show("RECLAIMED ISSUE within 30d (sorted by max upside)", touched_30, "max_upside_30d")
    show("NEVER reclaimed issue within 30d (sorted by drawdown, worst first)", never_30, "max_drawdown_30d", reverse=False)

    if args.csv:
        def cls(r):
            if f(r, "return_day7") is not None and f(r, "return_day7") >= 0: return "A (<=7d close)"
            if (f(r, "max_upside_30d") or -1) >= 0:
                return "C (touched<=30d)" if not (f(r,"return_day30") is not None and f(r,"return_day30")>=0) else "C (held d30)"
            return "E (never<=30d)"
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["company","symbol","listing_date","issue_price","issue_size_cr","qib_x",
                        "open%","day7%","day30%","day90%","max_upside%","max_dd%","class"])
            for r in disc:
                w.writerow([r["company_name"], r["nse_symbol"], r["listing_date"], num(r["issue_price"]),
                            num(r["issue_size_cr"]), num(r["qib_x"]),
                            num(r["return_listing_open"]), num(r["return_day7"]), num(r["return_day30"]),
                            num(r["return_day90"]), num(r["max_upside_30d"]), num(r["max_drawdown_30d"]), cls(r)])
        print(f"\nwrote per-IPO discount cohort → {args.csv}")

    print("\nResearch backtest, not a buy call. 'Reclaimed issue' is a far lower bar than the")
    print("dip-defense +15% test — read both: reclaiming issue != a tradeable profit.")

if __name__ == "__main__":
    main()
