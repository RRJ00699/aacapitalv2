#!/usr/bin/env python3
"""
_scripts/ipo/backtest_thesis.py
─────────────────────────────────────────────────────────────────────────────
Tests the "buy-at-open on quality" thesis against IPOs that have ALREADY listed.

Why this exists:
  The product question is not "does the dashboard render" — it's "can we tell,
  BEFORE listing, which IPOs are worth buying at open?". Every listed IPO in
  ipo_intelligence already carries its real outcome (listing_open vs issue_price).
  So we can answer that question right now, with data we already have.

What it does:
  1. Loads every row that has actually listed (has a listing_open / issue_price).
  2. Scores each one with score_ipo() — using ONLY pre-listing signals
     (subscription, GMP, anchors, valuation, size, BRLM, operator risk, regime).
  3. Computes the REAL listing-open return for each (from listing_open vs
     issue_price, which sidesteps the percent-vs-fraction mess in return_*).
  4. Reports, per recommendation bucket: count, avg/median open return, hit-rate.
     Compares to the naive baseline (buy EVERY IPO at open).
  5. Prints a DATA-COVERAGE table: % of rows where each signal is actually
     populated — so you can see which features are real vs empty ("nan").

score_ipo() is intentionally a standalone, transparent function so that — IF the
backtest shows an edge — it can be dropped straight into ipo_play_selector.py to
score live rows the same way.

Usage:
  python _scripts/ipo/backtest_thesis.py                 # full report
  python _scripts/ipo/backtest_thesis.py --csv out.csv   # per-IPO dump
  python _scripts/ipo/backtest_thesis.py --names         # show known winners/losers

Install:
  pip install psycopg2-binary python-dotenv
"""

import os
import sys
import math
import argparse
import statistics as stats
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(".env.local" if Path(".env.local").exists() else ".env")
except ImportError:
    pass

import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")

# ── thesis knobs (tune these to your framework) ───────────────────────────────
BUY_AT_OPEN_MIN  = 68   # score >= this  -> BUY_AT_OPEN
WAIT_VWAP_MIN    = 58   # score in [.., BUY_AT_OPEN_MIN) -> WAIT_FOR_VWAP
DAY3_MIN         = 48   # score in [.., WAIT_VWAP_MIN)   -> BUY_AFTER_DAY3
                        # below DAY3_MIN -> AVOID
WIN_THRESHOLD    = 5.0  # a listing-open gain >= this % counts as a "win"

# Signals we report coverage for (column -> human label, mapped to your points).
COVERAGE_FIELDS = [
    ("issue_size_cr",        "issue size (pt1)"),
    ("issue_price",          "issue price (pt1)"),
    ("ofs_pct",              "OFS % (pt2)"),
    ("fresh_issue_ratio",    "fresh issue ratio (pt2)"),
    ("ipo_pe",               "IPO PE (pt3/5)"),
    ("peer_median_pe",       "peer PE (pt3/5)"),
    ("valuation_premium_pct","valuation premium (pt3)"),
    ("brlm_names",           "BRLM names (pt3)"),
    ("brlm_score",           "BRLM score (pt3)"),
    ("anchor_quality",       "anchor quality (pt4)"),
    ("anchor_tier1_count",   "tier-1 anchors (pt4)"),
    ("qib_subscription_x",   "QIB subscription (pt4)"),
    ("retail_subscription_x","retail subscription (pt4)"),
    ("retail_category_pct",  "retail quota % (pt4)"),
    ("total_subscription_x", "total subscription"),
    ("gmp_max_pct",          "GMP max (pt6)"),
    ("gmp_momentum",         "GMP momentum (pt6)"),
    ("listing_day_vwap",     "listing VWAP (pt8)"),
    ("hit_uc_day1",          "hit UC day1 (pt7)"),
    ("india_vix",            "India VIX (pt10)"),
    ("listing_regime",       "market regime (pt10)"),
]

KNOWN = ["groww", "go digit", "aadhar housing", "bharti hexacom", "ntpc green",
         "canara robeco", "ixigo", "premier", "waaree", "netweb", "nsdl",
         "bajaj housing", "hdb", "afcons", "ola"]


def num(v, default=None):
    """Coerce messy DB values ('nan', '', '1,234.5', Decimal) to float or default."""
    if v is None:
        return default
    s = str(v).strip().replace(",", "")
    if s == "" or s.lower() in ("nan", "none", "null", "-", "--"):
        return default
    try:
        f = float(s)
        return default if math.isnan(f) else f
    except ValueError:
        return default


def listing_gain_pct(row):
    """REAL capturable return for a buyer who buys AT the listing open price.
    You don't get allotment, so the issue->open pop (allotment gain) is NOT yours.
    Your entry is the open; your exit is the listing-day close. Measure open->close.

    open->close is the realistic day-trade outcome. (open->high would be the
    best-case ceiling if you nailed the intraday top — see listing_gain_high.)"""
    lo = num(row.get("listing_open"))
    lc = num(row.get("listing_day_close"))
    if lo is not None and lo > 0 and lc is not None:
        return (lc - lo) / lo * 100.0
    # fallback: derive open->close from issue-price-based returns if both exist
    r_open  = num(row.get("return_listing_open"))   # issue->open %
    r_close = num(row.get("return_day1_close"))      # issue->close %
    if r_open is not None and r_close is not None:
        ro = r_open  if abs(r_open)  >= 1.5 else r_open  * 100.0
        rc = r_close if abs(r_close) >= 1.5 else r_close * 100.0
        # (1+rc)/(1+ro)-1  in pct terms
        return ((100.0 + rc) / (100.0 + ro) - 1.0) * 100.0
    return None


def listing_gain_high(row):
    """Best-case: open -> listing-day HIGH (only if you sold the intraday top)."""
    lo = num(row.get("listing_open"))
    hi = num(row.get("listing_day_high"))
    if lo is not None and lo > 0 and hi is not None:
        return (hi - lo) / lo * 100.0
    return None


# ── the thesis scorer (uses only PRE-listing signals) ─────────────────────────
def score_ipo(row):
    """Return (recommendation, confidence, score, reasons[]).
    Each signal only fires when its data is present, so empty columns simply
    don't contribute rather than dragging everything to neutral."""
    # ---- hard exclusions (user policy) -------------------------------------
    # Not interested in SME at all. And mainboard issues < Rs 150 cr list in a
    # 5% circuit band and get operator-manipulated (UC/LC games for 2-3 days),
    # so the listing-day play is untradeable. Exclude both outright before any
    # scoring so they never surface as candidates.
    if str(row.get("is_sme")).strip().lower() in ("true", "1", "yes", "t"):
        return "AVOID", 0, 0.0, ["EXCLUDED: SME"]
    _sz = num(row.get("issue_size_cr"))
    if _sz is not None and _sz < 150:
        return "AVOID", 0, 0.0, ["EXCLUDED: issue Rs %.0fcr < 150 (5%% band / operator risk)" % _sz]

    score = 50.0
    reasons = []

    def bump(delta, why):
        nonlocal score
        score += delta
        reasons.append(("+" if delta >= 0 else "") + f"{delta:g} {why}")

    # pt4 — institutional demand (QIB / total subscription)
    qib = num(row.get("qib_subscription_x"))
    if qib is not None:
        if qib >= 50:   bump(+15, f"QIB {qib:.0f}x")
        elif qib >= 20: bump(+8,  f"QIB {qib:.0f}x")
        elif qib < 3:   bump(-8,  f"weak QIB {qib:.1f}x")

    # pt4 — RETAIL demand + retail allocation category (your addition)
    retail = num(row.get("retail_subscription_x"))
    if retail is not None:
        if   retail >= 10: bump(+8, f"retail {retail:.0f}x")
        elif retail >= 3:  bump(+4, f"retail {retail:.0f}x")
        elif retail < 1:   bump(-6, f"retail undersubscribed {retail:.1f}x")
    # a 10% retail quota = QIB-route issue (often loss-making / richly valued) -> caution
    rcat = num(row.get("retail_category_pct"))
    if rcat is not None and rcat <= 12:
        bump(-4, f"only {rcat:.0f}% retail quota (QIB-route issue)")

    tot = num(row.get("total_subscription_x"))
    if tot is not None and tot >= 50:
        bump(+6, f"total sub {tot:.0f}x")

    # pt4 — anchors
    t1 = num(row.get("anchor_tier1_count"))
    if t1 is not None:
        if t1 >= 10:  bump(+10, f"{t1:.0f} tier-1 anchors")
        elif t1 > 0:  bump(+4,  f"{t1:.0f} tier-1 anchors")
    aq = (row.get("anchor_quality") or "").lower()
    if "weak" in aq:        bump(-6, "weak anchors")
    elif "tier-1" in aq or "strong" in aq: bump(+6, "strong anchors")

    # pt6 — GMP hype
    gmp = num(row.get("gmp_max_pct"))
    if gmp is not None:
        if gmp >= 30:   bump(+12, f"GMP {gmp:.0f}%")
        elif gmp >= 15: bump(+6,  f"GMP {gmp:.0f}%")
        elif gmp <= 2:  bump(-6,  "no GMP demand")

    # pt1 — issue size (avoid the 5% small-cap / SME band trap)
    size = num(row.get("issue_size_cr"))
    if size is not None:
        if size < 150:        bump(-10, f"small issue ₹{size:.0f}cr")
        elif size > 20000:    bump(-4,  f"jumbo issue ₹{size:.0f}cr")
        else:                 bump(+5,  f"mid issue ₹{size:.0f}cr")
    if str(row.get("is_sme")).lower() == "true":
        bump(-8, "SME (5% band)")

    # pt2 — OFS vs fresh (pure OFS treated cautiously without a growth flag)
    ofs = num(row.get("ofs_pct"))
    if ofs is not None and ofs > 80:
        bump(-4, f"mostly OFS {ofs:.0f}%")

    # pt3/5 — valuation
    vprem = num(row.get("valuation_premium_pct"))
    if vprem is not None and vprem > 50:
        bump(-8, f"rich valuation +{vprem:.0f}%")
    ipo_pe, peer_pe = num(row.get("ipo_pe")), num(row.get("peer_median_pe"))
    if ipo_pe and peer_pe and peer_pe > 0 and ipo_pe > peer_pe * 1.5:
        bump(-6, f"PE {ipo_pe:.0f} vs peer {peer_pe:.0f}")

    # pt3 — book runner track record
    brlm_neg = num(row.get("brlm_pct_negative"))
    if brlm_neg is not None and brlm_neg >= 40:
        bump(-5, f"BRLM {brlm_neg:.0f}% negative listings")
    brlm_sc = num(row.get("brlm_score"))
    if brlm_sc is not None:
        if   brlm_sc >= 70: bump(+6, f"strong BRLM track record ({brlm_sc:.0f})")
        elif brlm_sc <= 35: bump(-6, f"weak BRLM track record ({brlm_sc:.0f})")

    # operator risk (your 'notorious hype' point)
    op = num(row.get("operator_risk_score"))
    if op is not None:
        if op >= 50:   bump(-10, f"operator risk {op:.0f}")
        elif op >= 35: bump(-4,  f"operator risk {op:.0f}")

    # pt10 — market regime
    regime = (row.get("listing_regime") or "").lower()
    if regime in ("weak", "bear", "risk_off"):
        bump(-5, f"{regime} regime")
    vix = num(row.get("india_vix"))
    if vix is not None and vix >= 20:
        bump(-3, f"VIX {vix:.0f}")

    score = max(0.0, min(100.0, score))
    # A row with no populated signals can't be judged — don't pretend it's a buy.
    if not reasons:
        return "AVOID", round(score), score, ["insufficient data — not scored"]
    if   score >= BUY_AT_OPEN_MIN: rec = "BUY_AT_OPEN"
    elif score >= WAIT_VWAP_MIN:   rec = "WAIT_FOR_VWAP"
    elif score >= DAY3_MIN:        rec = "BUY_AFTER_DAY3"
    else:                          rec = "AVOID"
    return rec, round(score), score, reasons


# ── reporting ─────────────────────────────────────────────────────────────────
def pctile(vals, p):
    if not vals:
        return float("nan")
    s = sorted(vals)
    return s[min(len(s) - 1, int(p / 100 * len(s)))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="write per-IPO results to this CSV path")
    ap.add_argument("--names", action="store_true", help="show known winners/losers")
    args = ap.parse_args()

    if not DATABASE_URL:
        print("ERROR: set DATABASE_URL (or NEON_DATABASE_URL)", file=sys.stderr)
        sys.exit(1)

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM ipo_intelligence")
    all_rows = cur.fetchall()
    conn.close()

    # "listed" = anything with a real open outcome we can grade against
    listed = [r for r in all_rows if listing_gain_pct(r) is not None]
    total_n = len(all_rows)
    print(f"\nLoaded {total_n} rows; {len(listed)} have a gradable listing outcome.\n")

    # ── coverage ──
    print("=" * 64)
    print("DATA COVERAGE  (% of listed rows where the signal is populated)")
    print("=" * 64)
    for col, label in COVERAGE_FIELDS:
        present = sum(1 for r in listed if num(r.get(col)) is not None
                      or (isinstance(r.get(col), str) and r.get(col).strip().lower()
                          not in ("", "nan", "none", "null", "-")))
        pct = 100 * present / len(listed) if listed else 0
        bar = "█" * int(pct / 5)
        print(f"  {label:26s} {pct:5.1f}%  {bar}")

    # ── score + grade ──
    buckets = {"BUY_AT_OPEN": [], "WAIT_FOR_VWAP": [], "BUY_AFTER_DAY3": [], "AVOID": []}
    rows_out = []
    for r in listed:
        rec, conf, score, reasons = score_ipo(r)
        gain = listing_gain_pct(r)
        buckets[rec].append(gain)
        rows_out.append((r.get("company_name", "?"), rec, conf, round(gain, 1), "; ".join(reasons)))

    all_gains = [listing_gain_pct(r) for r in listed]
    base_mean = stats.mean(all_gains)
    base_win  = 100 * sum(1 for g in all_gains if g >= WIN_THRESHOLD) / len(all_gains)

    print("\n" + "=" * 64)
    print("THESIS PERFORMANCE  (REAL open->close return for a buyer AT the open)")
    print("=" * 64)
    print(f"  {'bucket':16s} {'n':>4s} {'avg%':>7s} {'median%':>8s} "
          f"{'win%':>6s} {'>10%':>6s} {'<-5%':>6s}")
    for rec in ("BUY_AT_OPEN", "WAIT_FOR_VWAP", "BUY_AFTER_DAY3", "AVOID"):
        g = buckets[rec]
        if not g:
            print(f"  {rec:16s} {0:>4d}      —        —      —      —      —")
            continue
        win  = 100 * sum(1 for x in g if x >= WIN_THRESHOLD) / len(g)
        big  = 100 * sum(1 for x in g if x >= 10) / len(g)
        bad  = 100 * sum(1 for x in g if x <= -5) / len(g)
        print(f"  {rec:16s} {len(g):>4d} {stats.mean(g):>7.1f} "
              f"{stats.median(g):>8.1f} {win:>5.0f}% {big:>5.0f}% {bad:>5.0f}%")
    print("-" * 64)
    print(f"  {'BASELINE (all)':16s} {len(all_gains):>4d} {base_mean:>7.1f} "
          f"{stats.median(all_gains):>8.1f} {base_win:>5.0f}%")
    print("\n  READ: if BUY_AT_OPEN's avg% and win% clearly beat BASELINE, the")
    print("  thesis is separating winners from the field. If it matches the")
    print("  baseline, the current signals aren't adding edge (likely because")
    print("  the inputs above are mostly empty — see coverage).")

    if args.names:
        print("\n" + "=" * 64)
        print("KNOWN NAMES")
        print("=" * 64)
        for name, rec, conf, gain, _ in sorted(rows_out, key=lambda x: -x[3]):
            if any(k in name.lower() for k in KNOWN):
                print(f"  {name[:34]:34s} -> {rec:14s} conf {conf:>3d}  actual {gain:+.1f}%")

    if args.csv:
        import csv
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["company", "recommendation", "confidence", "actual_open_pct", "reasons"])
            for row in sorted(rows_out, key=lambda x: -x[2]):
                w.writerow(row)
        print(f"\nWrote per-IPO results to {args.csv}")


if __name__ == "__main__":
    main()
