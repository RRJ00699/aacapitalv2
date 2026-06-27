#!/usr/bin/env python3
"""
_scripts/ipo/backtest_dip_defense.py
─────────────────────────────────────────────────────────────────────────────
Tests the "soft-listing dip-defense" thesis on IPOs that have ALREADY listed.

The thesis (yours):
  An IPO lists flat/negative, dips below issue price as weak hands sell, then
  institutions (anchors/QIBs/MFs) absorb the selling and the price recovers.
  Strategy: deploy remaining capital near the defended bottom, sell into recovery.

This answers the only question that matters before risking capital:
  "Historically, when an IPO lists soft and dips, how often does it actually
   recover — and how often does it just keep falling (capital lost)?"

Data used (all REAL columns on ipo_intelligence, written by
fetch_ipo_post_listing_returns.py; all returns are percent = (price/issue-1)*100):
  return_listing_open  issue->open %        (soft-open filter)
  return_day7          issue->day7 %        (underwater early?  → ordered dip)
  return_day30         issue->day30 %       (recovered by month-end?)
  return_day90         issue->day90 %       (still alive at a quarter?)
  max_drawdown_30d     deepest dip in 30d % (your ENTRY zone — the bottom)
  max_upside_30d       highest peak in 30d %(your EXIT zone  — the bounce)

Thesis cohort (configurable):
  soft open  : return_listing_open <= OPEN_MAX     (default +2%, i.e. flat/neg)
  dipped     : max_drawdown_30d   <= DIP_MIN        (default -5%, went underwater)
  ordered    : return_day7        <= WEAK_DAY7      (default 0, down at ~1 week)

Outcome:
  recovered (touch) : max_upside_30d >= UP_TARGET   (default +15%, bounce touched)
  recovered (hold)  : return_day30   >= UP_TARGET   (still up at month-end)
  failed            : return_day30 < 0 AND return_day90 < 0  (kept falling)

Also cross-references the recovered names against mf_scheme_holdings: did an MF
actually hold the stock within ~MF_WINDOW days of listing? (tests "MFs defend"
with real disclosure data, not a price guess).

Usage:
  python _scripts/ipo/backtest_dip_defense.py
  python _scripts/ipo/backtest_dip_defense.py --up-target 20 --dip-min -8
  python _scripts/ipo/backtest_dip_defense.py --csv dip_defense.csv
Env: DATABASE_URL  (reads .env / .env.local if python-dotenv is installed)
"""
import os, sys, csv, argparse, statistics as stats

try:
    from dotenv import load_dotenv
    load_dotenv(".env.local"); load_dotenv(".env")
except Exception:
    pass

import psycopg2
import psycopg2.extras

URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
if not URL:
    sys.exit("DATABASE_URL not set")


def num(v):
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def pct(n, d):
    return (100.0 * n / d) if d else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--open-max",  type=float, default=2.0,  help="soft open: return_listing_open <= this")
    ap.add_argument("--dip-min",   type=float, default=-5.0, help="dipped: max_drawdown_30d <= this")
    ap.add_argument("--weak-day7", type=float, default=0.0,  help="ordered: return_day7 <= this")
    ap.add_argument("--up-target", type=float, default=15.0, help="recovered: upside target %")
    ap.add_argument("--mf-window", type=int,   default=120,  help="days after listing to look for MF holding")
    ap.add_argument("--min-size-cr", type=float, default=200.0, help="exclude IPOs with issue size below this (crore)")
    ap.add_argument("--max-size-cr", type=float, default=None,  help="optional upper issue-size bound (crore)")
    ap.add_argument("--csv", help="write per-IPO cohort dump")
    args = ap.parse_args()

    conn = psycopg2.connect(URL)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Discover which issue-size column(s) actually exist on the table (schema is messy:
    # issue_size_cr / total_issue_amt_cr / issue_amount_cr / size_cr / ...). COALESCE the
    # ones present, preferring explicit-crore names; bare 'issue_size' last (ambiguous units).
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'ipo_intelligence'
    """)
    have_cols = {r["column_name"] for r in cur.fetchall()}
    size_pref = ["total_issue_amt_cr", "issue_size_cr", "issue_size_rs_cr",
                 "issue_amount_cr", "size_cr", "issue_size_crore", "issue_size"]
    size_cols = [c for c in size_pref if c in have_cols]
    size_expr = ("COALESCE(" + ", ".join(size_cols) + ")") if size_cols else "NULL"
    print(f"(issue-size source: {', '.join(size_cols) if size_cols else 'NONE FOUND'})")
    d15_expr = "return_day15" if "return_day15" in have_cols else "NULL"

    cur.execute(f"""
        SELECT company_name, nse_symbol, issue_price, listing_date,
               return_listing_open, return_day7, {d15_expr} AS return_day15,
               return_day30, return_day90,
               max_drawdown_30d, max_upside_30d,
               {size_expr} AS issue_size_cr
        FROM ipo_intelligence
        WHERE listing_date IS NOT NULL
    """)
    rows = [dict(r) for r in cur.fetchall()]
    # sanity-clamp size: valid crore figure roughly in [1, 200000]; else treat as unknown
    for r in rows:
        s = num(r.get("issue_size_cr"))
        r["issue_size_cr"] = s if (s is not None and 1 <= s <= 200000) else None
    total = len(rows)

    # ---- data coverage (so you know whether to run fetch_ipo_post_listing_returns first) ----
    needed = ["return_listing_open", "return_day7", "return_day30",
              "return_day90", "max_drawdown_30d", "max_upside_30d"]
    print("=" * 78)
    print(f"DIP-DEFENSE BACKTEST   ({total} listed IPOs in ipo_intelligence)")
    print("=" * 78)
    print("DATA COVERAGE (populate via fetch_ipo_post_listing_returns.py if low):")
    for c in needed:
        have = sum(1 for r in rows if num(r.get(c)) is not None)
        print(f"  {c:22s} {have:>4d}/{total}  ({pct(have, total):4.0f}%)")

    # rows usable for the full test = have the columns the cohort logic needs
    usable = [r for r in rows if all(num(r.get(c)) is not None
              for c in ["return_listing_open", "return_day7", "return_day30",
                        "max_drawdown_30d", "max_upside_30d"])]
    have_size = sum(1 for r in usable if r.get("issue_size_cr") is not None)
    print(f"\nUsable rows (all key return columns present): {len(usable)}  "
          f"(of which {have_size} have a valid issue size)")

    # ---- issue-size filter (the thesis is about INSTITUTIONAL defense, which only
    #      applies to issues big enough for institutions to matter) ----
    pre = len(usable)
    usable = [r for r in usable if r.get("issue_size_cr") is not None
              and r["issue_size_cr"] >= args.min_size_cr
              and (args.max_size_cr is None or r["issue_size_cr"] <= args.max_size_cr)]
    band = f">= {args.min_size_cr:.0f}cr" + (f" and <= {args.max_size_cr:.0f}cr" if args.max_size_cr else "")
    print(f"After issue-size filter ({band}): {len(usable)}  (dropped {pre - len(usable)})")
    if len(usable) < 20:
        print("\n⚠  Too few usable rows to trust the numbers. Run:")
        print("     python _scripts/ipo/fetch_ipo_post_listing_returns.py")
        print("   to backfill return_day7/30/90 + max_drawdown_30d/max_upside_30d, then re-run.")
        conn.close(); return

    # ---- baseline: among ALL usable, base rate of a >= up_target bounce in 30d ----
    base_touch = sum(1 for r in usable if num(r["max_upside_30d"]) >= args.up_target)
    print("\nBASELINE (every listed IPO, no filter):")
    print(f"  touched +{args.up_target:.0f}% within 30d : {base_touch}/{len(usable)}  ({pct(base_touch, len(usable)):.0f}%)")

    # ---- the thesis cohort ----
    cohort = [r for r in usable
              if num(r["return_listing_open"]) <= args.open_max
              and num(r["max_drawdown_30d"]) <= args.dip_min
              and num(r["return_day7"]) <= args.weak_day7]

    print("\n" + "-" * 78)
    print(f"THESIS COHORT: soft open (<=+{args.open_max:.0f}%) + dipped (<={args.dip_min:.0f}%) + down@day7")
    print("-" * 78)
    if not cohort:
        print("  no IPOs matched the cohort filters — loosen thresholds or backfill more data.")
        conn.close(); return

    n = len(cohort)
    touch = [r for r in cohort if num(r["max_upside_30d"]) >= args.up_target]
    hold  = [r for r in cohort if num(r["return_day30"])   >= args.up_target]
    failed = [r for r in cohort
              if num(r["return_day30"]) < 0 and num(r.get("return_day90")) is not None
              and num(r["return_day90"]) < 0]

    draw = [num(r["max_drawdown_30d"]) for r in cohort]
    up   = [num(r["max_upside_30d"]) for r in cohort]
    spread = [u - d for u, d in zip(up, draw)]

    print(f"  cohort size                       : {n}  ({pct(n, len(usable)):.0f}% of listed)")
    print(f"  RECOVERED (touched +{args.up_target:.0f}% peak)    : {len(touch)}/{n}  ({pct(len(touch), n):.0f}%)   "
          f"[baseline {pct(base_touch, len(usable)):.0f}%]")
    print(f"  RECOVERED (still up +{args.up_target:.0f}% @day30)  : {len(hold)}/{n}  ({pct(len(hold), n):.0f}%)")
    print(f"  FAILED  (neg @day30 AND @day90)   : {len(failed)}/{n}  ({pct(len(failed), n):.0f}%)  <-- capital-at-risk")
    print(f"  avg dip (entry zone)              : {stats.mean(draw):+.1f}%   (median {stats.median(draw):+.1f}%)")
    print(f"  avg peak (exit zone)              : {stats.mean(up):+.1f}%   (median {stats.median(up):+.1f}%)")
    print(f"  avg tradeable spread (peak-dip)   : {stats.mean(spread):.1f} pts   (median {stats.median(spread):.1f})")

    edge = pct(len(touch), n) - pct(base_touch, len(usable))
    verdict = ("EDGE — cohort beats baseline" if edge >= 10 else
               "WEAK — barely beats baseline" if edge >= 3 else
               "NO EDGE — cohort ≈ or worse than baseline (thesis not supported)")
    print(f"\n  EDGE vs baseline: {edge:+.0f} pts  →  {verdict}")

    # ---- price journey (actual rupees: issue x (1 + return/100)) ----
    def pr(issue, r):
        i, rr = num(issue), num(r)
        return f"{i * (1 + rr / 100):7.1f}" if (i is not None and rr is not None) else f"{'—':>7s}"

    has_d15 = any(num(r.get("return_day15")) is not None for r in cohort)
    print("\n" + "-" * 78)
    print("PRICE JOURNEY — cohort, sorted by day-30 (issue → open → d7 → d15 → d30 ; dip/peak = 30d low/high)")
    print("-" * 78)
    print(f"  {'company':30s} {'issue':>7s} {'open':>7s} {'d7':>7s} {'d15':>7s} {'d30':>7s} {'dip':>7s} {'peak':>7s}")
    for r in sorted(cohort, key=lambda x: (num(x["return_day30"]) if num(x["return_day30"]) is not None else -999),
                    reverse=True):
        iss = r.get("issue_price")
        print(f"  {(r.get('company_name') or '?')[:30]:30s} "
              f"{(num(iss) or 0):7.1f} "
              f"{pr(iss, r.get('return_listing_open'))} "
              f"{pr(iss, r.get('return_day7'))} "
              f"{pr(iss, r.get('return_day15'))} "
              f"{pr(iss, r.get('return_day30'))} "
              f"{pr(iss, r.get('max_drawdown_30d'))} "
              f"{pr(iss, r.get('max_upside_30d'))}")
    if not has_d15:
        print("\n  (d15 column is empty — add it by re-running fetch_ipo_post_listing_returns.py after the patch.)")

    # ---- MF cross-reference: did an MF actually hold the recovered names near listing? ----
    print("\n" + "-" * 78)
    print(f"MF CROSS-REFERENCE  (did MFs actually hold the recovered names within {args.mf_window}d of listing?)")
    print("-" * 78)
    mf_hit = mf_checked = 0
    mf_examples = []
    for r in touch:
        sym = (r.get("nse_symbol") or "").strip()
        ld = r.get("listing_date")
        if not sym or sym.lower() == "nan" or ld is None:
            continue
        mf_checked += 1
        cur.execute("""
            SELECT MIN(month) AS first_seen, COUNT(DISTINCT scheme_name) AS funds
            FROM mf_scheme_holdings
            WHERE nse_symbol = %s
              AND month >= %s AND month <= %s + (%s || ' days')::interval
        """, (sym, ld, ld, args.mf_window))
        g = cur.fetchone()
        if g and g["first_seen"]:
            mf_hit += 1
            if len(mf_examples) < 12:
                mf_examples.append((r.get("company_name", sym), sym, g["first_seen"], g["funds"]))
    if mf_checked:
        print(f"  recovered names with an MF holding near listing: {mf_hit}/{mf_checked}  ({pct(mf_hit, mf_checked):.0f}%)")
        print("  (low % may just mean MF disclosure history doesn't reach that far back —")
        print("   the Screener/disclosure universe is the limit, not necessarily the thesis.)")
        for name, sym, fs, funds in mf_examples:
            print(f"     {name[:34]:34s} {sym:12s} MF seen {fs}  ({funds} fund/s)")
    else:
        print("  no recovered names had a usable nse_symbol + listing_date to check.")

    if args.csv:
        def prc(issue, r):
            i, rr = num(issue), num(r)
            return round(i * (1 + rr / 100), 2) if (i is not None and rr is not None) else None
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["company", "nse_symbol", "listing_date", "issue_price",
                        "px_open", "px_day7", "px_day15", "px_day30", "px_dip", "px_peak",
                        "open%", "day7%", "day15%", "day30%", "day90%",
                        "max_dd_30d%", "max_up_30d%", "issue_size_cr", "recovered_touch"])
            for r in cohort:
                iss = r.get("issue_price")
                w.writerow([r.get("company_name"), r.get("nse_symbol"), r.get("listing_date"), num(iss),
                            prc(iss, r.get("return_listing_open")), prc(iss, r.get("return_day7")),
                            prc(iss, r.get("return_day15")), prc(iss, r.get("return_day30")),
                            prc(iss, r.get("max_drawdown_30d")), prc(iss, r.get("max_upside_30d")),
                            r.get("return_listing_open"), r.get("return_day7"), r.get("return_day15"),
                            r.get("return_day30"), r.get("return_day90"),
                            r.get("max_drawdown_30d"), r.get("max_upside_30d"), r.get("issue_size_cr"),
                            num(r["max_upside_30d"]) >= args.up_target])
        print(f"\nwrote per-IPO cohort dump → {args.csv}")

    conn.close()
    print("\nNote: this is a research backtest, not a buy recommendation. Capital protection first —")
    print("the FAILED rate above is the number that sizes your downside if the floor doesn't hold.")


if __name__ == "__main__":
    main()
