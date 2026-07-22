#!/usr/bin/env python3
"""rule_validation.py — Phase 10 Rule Validation Engine v1 (2026-07-22).

Validates every static rule against the GOLDEN OBJECT (ipo_gold: one table,
inputs + candles_json together). Nothing is a black box: every result row
carries the dataset, SQL inputs, filters, date range, n, win rate, average/
median return, max drawdown, expectancy, a binomial significance check vs
baseline, and the backtest + rule versions with a timestamp.

Definitions (spec §2A, unchanged from production):
  outcome return = best close within the captured window vs LISTING OPEN
                   (a CEILING measure — not an executable exit)
  win            = that return > 0
  baseline       = the same measure over the whole eligible universe

Run:  python _scripts/rule_validation.py            # report only
      python _scripts/rule_validation.py --store    # + persist results
Reads ipo_gold only. --store writes rule_validation_results (durable,
schema_sync-owned DDL). PC-runnable (DATABASE_URL = Neon).
"""
import argparse
import json
import math
import os
import statistics
import sys
from datetime import datetime, timezone

BACKTEST_VERSION = "rv1-2026-07-22"
OUTCOME = "ceiling"  # set from --outcome at runtime
DATASET = "ipo_gold (VIEW: ipo_consolidated ⟕ ipo_golden) · candles_json listing→lock-in"
# DECADE LOCK (owner, 2026-07-24): the accurate dataset + ALL backtests
# cover 2016-2026. Older rows may exist but earn no effort and no weight.
ELIGIBILITY = ("COALESCE(is_sme,false)=false AND (issue_size_cr IS NULL OR issue_size_cr>=200) "
               "AND company_name !~* '\\y(REIT|InvIT)\\y' AND candles_json IS NOT NULL "
               "AND issue_price > 0 AND listing_date >= DATE '{SINCE}-01-01'")

# rule_id -> (version, human filter, python predicate on row dict)
RULES = {
    "anchors_30plus": ("v1", "anchor_count >= 30", lambda r: (r["anchor_count"] or 0) >= 30),
    "anchors_50plus": ("v1", "anchor_count >= 50", lambda r: (r["anchor_count"] or 0) >= 50),
    # AMOUNT variants (2026-07-22): NSE mining yields anchor AMOUNT not
    # investor count — 433 IPOs carry anchor_amount_cr. SEBI caps the anchor
    # book at 60% of QIB (~30% of a 50%-QIB issue): 20%/30% of issue size
    # are the natural strength thresholds.
    "anchor_amt_20pct": ("v1", "anchor_amount_cr/issue_size_cr >= 0.20",
        lambda r: (r.get("anchor_amount_cr") or 0) > 0 and (r.get("issue_size_cr") or 0) > 0
                  and float(r["anchor_amount_cr"]) / float(r["issue_size_cr"]) >= 0.20),
    "anchor_amt_30pct": ("v1", "anchor_amount_cr/issue_size_cr >= 0.30",
        lambda r: (r.get("anchor_amount_cr") or 0) > 0 and (r.get("issue_size_cr") or 0) > 0
                  and float(r["anchor_amount_cr"]) / float(r["issue_size_cr"]) >= 0.30),
    # CANDIDATE PACK (pattern-mining 2026-07-22; thresholds from the table's
    # own medians). Promotion bar unchanged: beat baseline here or stay off
    # the card. gap rule is tradeable (the open prints before the hold).
    "qib_15x": ("v1", "final_qib >= 15", lambda r: r.get("final_qib") is not None and float(r["final_qib"]) >= 15),
    "qib_25x": ("v1", "final_qib >= 25", lambda r: r.get("final_qib") is not None and float(r["final_qib"]) >= 25),
    "total_10x": ("v1", "final_total >= 10", lambda r: r.get("final_total") is not None and float(r["final_total"]) >= 10),
    "bnii_20x": ("v1", "bnii_x >= 20", lambda r: r.get("bnii_x") is not None and float(r["bnii_x"]) >= 20),
    "gap_pos_hold": ("v1", "listing_gap_pct > 0", lambda r: r.get("listing_gap_pct") is not None and float(r["listing_gap_pct"]) > 0),
    "pb_high_7": ("v1", "price_to_book >= 7", lambda r: r.get("price_to_book") is not None and float(r["price_to_book"]) >= 7),
    "ofs_nonzero": ("v1", "ofs_pct > 0 (ARTIFACT TEST)", lambda r: r.get("ofs_pct") is not None and float(r["ofs_pct"]) > 0),
    # DISCOVERED RULES (owner scenario session 2026-07-22 — the first rules
    # the platform found rather than inherited; template result: 76.2% held
    # vs 60.1% base, n=42, p~.018):
    "stability_stack": ("v1", "price_to_book >= 7 AND anchor_count >= 30",
        lambda r: r.get("price_to_book") is not None and float(r["price_to_book"]) >= 7
                  and (r.get("anchor_count") or 0) >= 30),
    "avoid_cold_skip": ("v1", "score_band = AVOID AND final_total < 5 (SKIP signal)",
        lambda r: (r.get("score_band") == "AVOID") and r.get("final_total") is not None
                  and float(r["final_total"]) < 5),
    "mega_issue_2000cr": ("v1", "issue_size_cr >= 2000", lambda r: (r["issue_size_cr"] or 0) >= 2000),
    "reasonable_pe_70": ("v1", "ipo_pe > 0 AND ipo_pe <= 70", lambda r: r["ipo_pe"] is not None and 0 < r["ipo_pe"] <= 70),
    "qib_50x": ("v1", "final_qib >= 50", lambda r: (r["final_qib"] or 0) >= 50),
    "band_strong": ("v1", "score_band = 'STRONG'", lambda r: r["score_band"] == "STRONG"),
    "band_favorable": ("v1", "score_band = 'FAVORABLE'", lambda r: r["score_band"] == "FAVORABLE"),
    "band_avoid_skip": ("v1", "score_band = 'AVOID' (expect LOW win rate)", lambda r: r["score_band"] == "AVOID"),
}


def outcome(row):
    """(win, best_return_pct, max_drawdown_pct) from candles vs listing open."""
    candles = row["candles_json"]
    if isinstance(candles, str):
        candles = json.loads(candles)
    if not candles:
        return None
    open_px = float(candles[0]["o"])
    if open_px <= 0:
        return None
    closes = [float(k["c"]) for k in candles]
    lows = [float(k["l"]) for k in candles]
    best = max(closes) if OUTCOME == "ceiling" else closes[-1]
    ret = (best - open_px) / open_px * 100
    dd = (min(lows) - open_px) / open_px * 100
    return (ret > 0, ret, dd)


def binom_p_greater(k, n, p0):
    """one-sided P(X >= k | n, p0) — normal approx above n=30, exact below."""
    if n == 0:
        return 1.0
    if n <= 30:
        from math import comb
        return sum(comb(n, i) * p0**i * (1 - p0)**(n - i) for i in range(k, n + 1))
    mu, sd = n * p0, math.sqrt(n * p0 * (1 - p0)) or 1e-9
    z = (k - 0.5 - mu) / sd
    return 0.5 * math.erfc(z / math.sqrt(2))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", action="store_true")
    ap.add_argument("--outcome", choices=["ceiling", "hold", "both"], default="ceiling",
        help="ceiling = best close in window vs open (did a profitable exit EXIST); "
             "hold = LAST close vs open (did it STAY positive to the lock)")
    ap.add_argument("--since", type=int, default=2016,
        help="listing-date floor year (default 2016 = DECADE LOCK; e.g. --since 2000 for an inception COMPARISON run — the doctrine stays 2016)")
    a = ap.parse_args()
    if a.outcome == "both":  # ONE RUN (owner 2026-07-22): both yardsticks, back to back
        import subprocess
        for oc in ("ceiling", "hold"):
            print(f"\n{'='*78}\n  OUTCOME: {oc.upper()}\n{'='*78}")
            r = subprocess.run([sys.executable, os.path.abspath(__file__),
                                "--outcome", oc, "--since", str(a.since)]
                               + (["--store"] if a.store else []))
            if r.returncode != 0:
                return r.returncode
        return 0
    ELIG = ELIGIBILITY.replace("{SINCE}", str(a.since))
    global OUTCOME, BACKTEST_VERSION
    OUTCOME = a.outcome
    if a.outcome != "ceiling":
        BACKTEST_VERSION = f"{BACKTEST_VERSION}-hold"
    if a.since != 2016:
        BACKTEST_VERSION = f"{BACKTEST_VERSION}-since{a.since}"
    import psycopg2
    import psycopg2.extras
    db = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not db:
        sys.exit("DATABASE_URL not set")
    conn = psycopg2.connect(db, connect_timeout=25)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET statement_timeout = '120s'")
    q = f"""SELECT company_name, listing_date, anchor_count, anchor_amount_cr, issue_size_cr, ipo_pe,
                   final_qib, final_total, bnii_x, listing_gap_pct, price_to_book,
                   ofs_pct, score_band, issue_price, candles_json
            FROM ipo_gold WHERE {ELIG}"""
    cur.execute(q)
    rows = []
    for r in cur.fetchall():
        r = dict(r)
        for k in ("anchor_count", "issue_size_cr", "ipo_pe", "final_qib", "issue_price"):
            r[k] = float(r[k]) if r[k] is not None else None
        o = outcome(r)
        if o:
            r["_outcome"] = o
            rows.append(r)
    n_all = len(rows)
    if not n_all:
        sys.exit("no scoreable rows — run consolidate first")
    base_wins = sum(1 for r in rows if r["_outcome"][0])
    base_rate = base_wins / n_all
    dates = sorted(str(r["listing_date"]) for r in rows if r["listing_date"])
    date_range = f"{dates[0]}..{dates[-1]}" if dates else "n/a"
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

    print(f"RULE VALIDATION · {BACKTEST_VERSION} · {ts}")
    print(f"dataset: {DATASET}")
    print(f"filters: {ELIG}")
    print(f"outcome = {a.outcome} ({'best close in window' if a.outcome=='ceiling' else 'LAST close — stayed positive to lock'} vs listing open)")
    print(f"universe n={n_all} · date range {date_range} · BASELINE win {base_rate*100:.1f}%")
    print(f"{'rule':20} {'n':>4} {'win%':>6} {'avg%':>7} {'med%':>7} {'maxDD%':>7} {'expct%':>7} {'p-vs-base':>9}  beats?")
    results = []
    for rid, (rver, human, pred) in RULES.items():
        sub = [r for r in rows if pred(r)]
        n = len(sub)
        if n == 0:
            print(f"{rid:20} {0:>4}  — no qualifying IPOs in the golden universe")
            continue
        rets = [r["_outcome"][1] for r in sub]
        wins = sum(1 for r in sub if r["_outcome"][0])
        dds = [r["_outcome"][2] for r in sub]
        win = wins / n
        avg, med = statistics.mean(rets), statistics.median(rets)
        maxdd = min(dds)
        expct = win * avg + (1 - win) * statistics.mean([x for x in rets if x <= 0] or [0])
        p = binom_p_greater(wins, n, base_rate)
        beats = win > base_rate and p < 0.10
        print(f"{rid:20} {n:>4} {win*100:>5.1f}% {avg:>6.1f}% {med:>6.1f}% {maxdd:>6.1f}% {expct:>6.1f}% {p:>9.3f}  {'YES' if beats else 'no'}")
        results.append((rid, rver, human, n, win, avg, med, maxdd, expct, p, beats))

    if a.store and results:
        cur2 = conn.cursor()
        for rid, rver, human, n, win, avg, med, maxdd, expct, p, beats in results:
            cur2.execute("""INSERT INTO rule_validation_results
                (rule_id, rule_version, backtest_version, dataset, sql_filter, rule_filter,
                 date_range, n, win_rate, avg_return, median_return, max_drawdown,
                 expectancy, p_vs_baseline, beats_baseline, baseline_win_rate, universe_n, run_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (rid, rver, BACKTEST_VERSION, DATASET, ELIG, human, date_range,
                 n, win, avg, med, maxdd, expct, p, beats, base_rate, n_all, ts))
        conn.commit()
        print(f"STORED {len(results)} rows -> rule_validation_results ({BACKTEST_VERSION})")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
