#!/usr/bin/env python3
"""
ipo_factor_dump.py — one row per listed IPO, every factor as a column, sorted by the
REAL open-buy gain (open->close). Exploratory: look at what separates winners before
committing to any model.

Honest about coverage: columns that don't exist or are empty in ipo_intelligence show
blank — they are NOT faked. PCR and peer-valuation are currently empty (see the
"MISSING FACTORS" note the script prints) — those need importing from Chittorgarh first.

Gains shown per IPO:
  pop   = issue -> open      (the allotment pop — NOT yours unless you got allotment)
  o->c  = open  -> close     (buyer-at-open day trade — the realistic capturable return)
  o->hi = open  -> high      (best case: sold the intraday top)

Run:  python _scripts/ipo/ipo_factor_dump.py            (console top/bottom + summary)
      python _scripts/ipo/ipo_factor_dump.py --csv ipo_factors.csv   (full sortable CSV)
Env:  DATABASE_URL (or NEON_DATABASE_URL)
"""
import os, sys, math, argparse, csv
import psycopg2, psycopg2.extras

URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
if not URL:
    sys.exit("DATABASE_URL not set")


def num(v):
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if s == "" or s.lower() in ("nan", "none", "null", "-", "--"):
        return None
    try:
        f = float(s)
        return None if math.isnan(f) else f
    except ValueError:
        return None


# requested factors -> candidate column names (first that exists+populated wins)
FACTOR_COLS = {
    "regime":        ["listing_regime", "market_regime"],
    "pcr":           ["pcr", "nifty_pcr", "put_call_ratio"],
    "vix":           ["india_vix", "vix"],
    "brlm_score":    ["brlm_score"],
    "brlm":          ["brlm_names", "lead_managers", "brlm"],
    "anchors":       ["anchor_tier1_count", "anchor_count", "num_anchors"],
    "anchor_q":      ["anchor_quality"],
    "ofs_pct":       ["ofs_pct"],
    "fresh_ratio":   ["fresh_issue_ratio"],
    "size_cr":       ["issue_size_cr", "issue_size"],
    "ipo_pe":        ["ipo_pe", "pe", "pe_ratio"],
    "peer_pe":       ["peer_median_pe", "peer_pe", "sector_pe"],
    "val_premium":   ["valuation_premium_pct"],
    "roe":           ["roe", "roe_pct"],
    "pb":            ["pb", "pb_ratio", "price_to_book"],
    "eps":           ["eps", "eps_diluted"],
    "sector":        ["sector", "industry"],
    "qib_x":         ["qib_subscription_x"],
    "total_x":       ["total_subscription_x"],
    "gmp_max":       ["gmp_max_pct"],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="write full sortable table to this CSV path")
    ap.add_argument("--top", type=int, default=20, help="console top/bottom N")
    args = ap.parse_args()

    conn = psycopg2.connect(URL)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM ipo_intelligence")
    rows = cur.fetchall()
    conn.close()
    if not rows:
        sys.exit("ipo_intelligence is empty")

    present_cols = set(rows[0].keys())
    # resolve each factor to the first candidate column that actually exists
    resolved, missing = {}, []
    for fac, cands in FACTOR_COLS.items():
        col = next((c for c in cands if c in present_cols), None)
        resolved[fac] = col
        if col is None:
            missing.append(fac)

    def gains(r):
        ip = num(r.get("issue_price"))
        lo = num(r.get("listing_open"))
        lc = num(r.get("listing_day_close"))
        hi = num(r.get("listing_day_high"))
        pop  = (lo - ip) / ip * 100 if (ip and ip > 0 and lo is not None) else None
        # prefer the clean backfilled columns; fall back to computing from prices
        oc   = num(r.get("gain_open_close"))
        if oc is None and lo and lo > 0 and lc is not None: oc = (lc - lo) / lo * 100
        ohi  = num(r.get("gain_open_high"))
        if ohi is None and lo and lo > 0 and hi is not None: ohi = (hi - lo) / lo * 100
        h5  = num(r.get("return_open_5d"))
        h20 = num(r.get("return_open_20d"))
        return pop, oc, ohi, h5, h20

    recs = []
    for r in rows:
        pop, oc, ohi, h5, h20 = gains(r)
        if oc is None or h20 is None:   # need a real open->close AND a 20-day hold
            continue
        rec = {"company": (r.get("company_name") or "?")[:34],
               "pop": pop, "o_c": oc, "o_hi": ohi, "hold5": h5, "hold20": h20}
        for fac, col in resolved.items():
            rec[fac] = r.get(col) if col else None
        recs.append(rec)

    # sort by the 20-day hold (open->20d) — that is where winners/losers actually spread.
    recs.sort(key=lambda x: x["hold20"], reverse=True)

    # ── coverage of each requested factor among the studied IPOs ──
    print(f"\n{len(recs)} IPOs with a real open->close outcome.\n")
    print("=" * 70)
    print("REQUESTED-FACTOR COVERAGE (within these IPOs)")
    print("=" * 70)
    for fac in FACTOR_COLS:
        col = resolved[fac]
        if col is None:
            print(f"  {fac:12s}  —  NO COLUMN (needs importing)"); continue
        filled = sum(1 for x in recs if num(x[fac]) is not None
                     or (isinstance(x[fac], str) and x[fac].strip()
                         and x[fac].strip().lower() not in ("nan", "none", "null", "-")))
        pct = 100 * filled / len(recs)
        flag = "  ← EMPTY" if pct < 1 else ""
        print(f"  {fac:12s}  {pct:5.1f}%  (col: {col}){flag}")
    if missing:
        print(f"\nMISSING entirely (no such column): {', '.join(missing)}")

    # ── console: top & bottom N by open->close ──
    def line(x):
        def f(v, w=6, d=1):
            v = num(v)
            return (f"{v:>{w}.{d}f}" if v is not None else " " * w)
        reg = (str(x["regime"])[:7] if x["regime"] else "")
        brlm = (str(x["brlm"])[:16] if x["brlm"] else "")
        return (f"  {x['company']:30s} hold20{f(x['hold20'],6)}%  hold5{f(x['hold5'],6)}%  "
                f"o->c{f(x['o_c'],6)}%  QIB{f(x['qib_x'],5,0)}  GMP{f(x['gmp_max'],5,0)}  "
                f"ofs{f(x['ofs_pct'],5,0)}  PE{f(x['ipo_pe'],5,0)}  BRLM{f(x['brlm_score'],4,0)}  "
                f"{reg:7s} {brlm}")

    print("\n" + "=" * 70)
    print(f"TOP {args.top} by 20-DAY HOLD (buy at open, hold 20 trading days)")
    print("=" * 70)
    for x in recs[:args.top]:
        print(line(x))
    print("\n" + "=" * 70)
    print(f"BOTTOM {args.top} by 20-DAY HOLD")
    print("=" * 70)
    for x in recs[-args.top:]:
        print(line(x))

    # ── quick win/loss split of the top vs bottom tercile on each numeric factor ──
    import statistics as st
    def avg(vals):
        vals = [num(v) for v in vals if num(v) is not None]
        return st.mean(vals) if vals else None
    third = max(1, len(recs) // 3)
    winners, losers = recs[:third], recs[-third:]
    print("\n" + "=" * 70)
    print("WINNERS (top third) vs LOSERS (bottom third) — avg of each factor")
    print("=" * 70)
    print(f"  {'factor':12s} {'winners':>10s} {'losers':>10s}")
    for fac in ["qib_x", "total_x", "gmp_max", "anchors", "ofs_pct", "fresh_ratio",
                "ipo_pe", "brlm_score", "size_cr", "vix", "pcr"]:
        if resolved.get(fac) is None:
            continue
        wv, lv = avg(w[fac] for w in winners), avg(l[fac] for l in losers)
        if wv is None and lv is None:
            continue
        ws = f"{wv:10.1f}" if wv is not None else " " * 10
        ls = f"{lv:10.1f}" if lv is not None else " " * 10
        print(f"  {fac:12s} {ws} {ls}")
    print("\n  READ: a factor only separates winners from losers if its winner-avg and")
    print("  loser-avg differ meaningfully. If they're ~equal, that factor isn't sorting")
    print("  the open-buy outcome. (open->close already proved ~flat overall, so expect")
    print("  most of these to be close — the point is to SEE which, if any, diverge.)")

    if args.csv:
        cols = ["company", "pop", "o_c", "o_hi", "hold5", "hold20"] + list(FACTOR_COLS.keys())
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(cols)
            for x in recs:
                w.writerow([x.get(c) for c in cols])
        print(f"\nWrote full sortable table to {args.csv} ({len(recs)} IPOs).")


if __name__ == "__main__":
    main()
