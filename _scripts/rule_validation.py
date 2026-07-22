#!/usr/bin/env python3
"""rule_validation.py — Rule Validation Engine v2 (rv2, 2026-07-22).

RESEARCH-GOVERNANCE MANDATE (owner, 2026-07-22): a finding is NOT canonical
until every result row carries a full reproducibility block and full
statistics. rv2 adds, per rule per run:
  §1 reproducibility — dataset, SQL eligibility, rule filter, date range,
     dataset/rule/backtest versions, timestamp, GIT HASH of the code, and an
     EXCLUSION LEDGER (rows available → excluded per reason → scoreable).
  §2 full statistics — Wilson CI95 on the win rate, odds ratio vs the rest of
     the universe (Haldane +0.5 on zero cells), absolute + relative lift,
     exact p with the TEST NAME recorded, Benjamini–Hochberg FDR q-value
     across all rules in the run (Bonferroni deliberately rejected: ×19 kills
     every finding incl. mega .047; owner accepts BH may still retire rules),
     and post-hoc power at the observed effect.
  §3 labeling — every stored row carries finding_status
     'DISCOVERY — awaiting out-of-sample confirmation' until a holdout
     confirms it. No always/never wording anywhere.

Definitions (spec §2A, unchanged from production):
  outcome return = best close within the captured window vs LISTING OPEN
                   (a CEILING measure — not an executable exit)
  hold outcome   = LAST close vs listing open (stayed positive to the lock)
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

BACKTEST_VERSION = "rv2-2026-07-22"
OUTCOME = "ceiling"  # set from --outcome at runtime
DATASET = "ipo_gold (VIEW: ipo_consolidated \u27d5 ipo_golden) \u00b7 candles_json listing\u2192lock-in"
FINDING_STATUS = "DISCOVERY — awaiting out-of-sample confirmation"
FDR_ALPHA = 0.10  # promotion bar under BH; mirrors the historic p<0.10 flag
# DECADE LOCK (owner, permanent): the accurate dataset + ALL backtests
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


def git_hash():
    """Short commit hash of the code that produced the run (mandate §1)."""
    try:
        import subprocess
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             cwd=os.path.dirname(os.path.abspath(__file__)),
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def wilson_ci95(k, n):
    """Wilson score 95% interval for a binomial proportion — behaves at the
    small n this table lives on, unlike the Wald interval."""
    if n == 0:
        return (0.0, 1.0)
    z = 1.959963984540054
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, centre - half), min(1.0, centre + half))


def odds_ratio(w_in, l_in, w_out, l_out):
    """Rule wins/losses vs REST of universe. Haldane–Anscombe +0.5 on any
    zero cell so 100%/0% subsets stay finite and honest about uncertainty."""
    if min(w_in, l_in, w_out, l_out) == 0:
        w_in, l_in, w_out, l_out = (x + 0.5 for x in (w_in, l_in, w_out, l_out))
    return (w_in / l_in) / (w_out / l_out)


def binom_p_greater(k, n, p0):
    """One-sided P(X >= k | n, p0). Exact binomial to n=1000 (float-safe in
    Python), normal approx w/ continuity correction above. Returns
    (p, test_name) so the test used rides in provenance (mandate §2)."""
    if n == 0:
        return 1.0, "n/a"
    if n <= 1000:
        from math import comb
        p = sum(comb(n, i) * p0**i * (1 - p0)**(n - i) for i in range(k, n + 1))
        return min(1.0, p), "binomial exact, one-sided vs baseline"
    mu, sd = n * p0, math.sqrt(n * p0 * (1 - p0)) or 1e-9
    z = (k - 0.5 - mu) / sd
    return 0.5 * math.erfc(z / math.sqrt(2)), "binomial normal approx (continuity-corrected), one-sided vs baseline"


def power_observed(n, p0, p1, alpha=0.05):
    """Post-hoc power (normal approx, one-sided alpha=0.05) to detect the
    OBSERVED rate p1 vs baseline p0 at this n. Reported for transparency
    (mandate §2): its honest use is judging whether n was ever big enough to
    see an effect this size — not rescuing a null result."""
    if n == 0 or p1 <= p0:
        return 0.0
    z_a = 1.6448536269514722
    num = (p1 - p0) * math.sqrt(n) - z_a * math.sqrt(p0 * (1 - p0))
    den = math.sqrt(p1 * (1 - p1)) or 1e-9
    return 0.5 * math.erfc(-(num / den) / math.sqrt(2))


def bh_fdr(pvals):
    """Benjamini–Hochberg step-up q-values across the rules tested in ONE run
    (mandate §2). Chosen over Bonferroni deliberately — owner accepts BH may
    still retire rules; p-values alone are insufficient."""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    q = [0.0] * m
    running = 1.0
    for back, idx in enumerate(reversed(order)):
        rank = m - back
        running = min(running, pvals[idx] * m / rank)
        q[idx] = running
    return q


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

    # ── EXCLUSION LEDGER (mandate §1): rows available → why excluded → scoreable.
    # Reason counts are INDEPENDENT (a row may match several reasons).
    ledger = {"note": "reason counts are independent; a row may match several"}
    cur.execute("SELECT COUNT(*) AS c FROM ipo_gold")
    ledger["rows_available"] = cur.fetchone()["c"]
    for label, clause in (
        ("excluded_sme", "COALESCE(is_sme,false)=true"),
        ("excluded_small_issue_lt200cr", "issue_size_cr IS NOT NULL AND issue_size_cr < 200"),
        ("excluded_reit_invit", "company_name ~* '\\y(REIT|InvIT)\\y'"),
        ("excluded_no_candles", "candles_json IS NULL"),
        ("excluded_bad_issue_price", "issue_price IS NULL OR issue_price <= 0"),
        ("excluded_null_listing_date", "listing_date IS NULL"),
        (f"excluded_pre_{a.since}", f"listing_date < DATE '{a.since}-01-01'"),
    ):
        cur.execute(f"SELECT COUNT(*) AS c FROM ipo_gold WHERE {clause}")
        ledger[label] = cur.fetchone()["c"]

    q = f"""SELECT company_name, listing_date, anchor_count, anchor_amount_cr, issue_size_cr, ipo_pe,
                   final_qib, final_total, bnii_x, listing_gap_pct, price_to_book,
                   ofs_pct, score_band, issue_price, candles_json
            FROM ipo_gold WHERE {ELIG}"""
    cur.execute(q)
    rows, fetched = [], 0
    for r in cur.fetchall():
        fetched += 1
        r = dict(r)
        for k in ("anchor_count", "issue_size_cr", "ipo_pe", "final_qib", "issue_price"):
            r[k] = float(r[k]) if r[k] is not None else None
        o = outcome(r)
        if o:
            r["_outcome"] = o
            rows.append(r)
    n_all = len(rows)
    ledger["eligible"] = fetched
    ledger["excluded_unscoreable_candles"] = fetched - n_all
    ledger["scoreable"] = n_all
    if not n_all:
        sys.exit("no scoreable rows — run consolidate first")
    base_wins = sum(1 for r in rows if r["_outcome"][0])
    base_rate = base_wins / n_all
    dates = sorted(str(r["listing_date"]) for r in rows if r["listing_date"])
    date_range = f"{dates[0]}..{dates[-1]}" if dates else "n/a"
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    ghash = git_hash()

    print(f"RULE VALIDATION \u00b7 {BACKTEST_VERSION} \u00b7 {ts} \u00b7 git {ghash}")
    print(f"dataset: {DATASET}")
    print(f"filters: {ELIG}")
    print(f"status:  {FINDING_STATUS}")
    print("ledger:  " + " ".join(f"{k}={v}" for k, v in ledger.items() if k != "note"))
    print(f"outcome = {a.outcome} ({'best close in window' if a.outcome=='ceiling' else 'LAST close — stayed positive to lock'} vs listing open)")
    print(f"universe n={n_all} \u00b7 date range {date_range} \u00b7 BASELINE win {base_rate*100:.1f}%")
    print(f"{'rule':20} {'n':>4} {'win%':>6} {'ci95':>13} {'OR':>6} {'lift':>6} {'med%':>6} {'expct%':>7} {'p':>7} {'q(BH)':>7} {'power':>5}  beats?")
    results = []
    for rid, (rver, human, pred) in RULES.items():
        sub = [r for r in rows if pred(r)]
        n = len(sub)
        if n == 0:
            print(f"{rid:20} {0:>4}  \u2014 no qualifying IPOs in the golden universe")
            continue
        rets = [r["_outcome"][1] for r in sub]
        wins = sum(1 for r in sub if r["_outcome"][0])
        dds = [r["_outcome"][2] for r in sub]
        win = wins / n
        avg, med = statistics.mean(rets), statistics.median(rets)
        maxdd = min(dds)
        expct = win * avg + (1 - win) * statistics.mean([x for x in rets if x <= 0] or [0])
        p, test_name = binom_p_greater(wins, n, base_rate)
        ci_lo, ci_hi = wilson_ci95(wins, n)
        orat = odds_ratio(wins, n - wins, base_wins - wins, (n_all - base_wins) - (n - wins))
        abs_lift = win - base_rate            # percentage points
        rel_lift = (win / base_rate - 1) if base_rate > 0 else 0.0
        power = power_observed(n, base_rate, win)
        results.append([rid, rver, human, n, wins, win, avg, med, maxdd, expct,
                        p, test_name, ci_lo, ci_hi, orat, abs_lift, rel_lift, power])
    qvals = bh_fdr([r[10] for r in results])
    for r, qv in zip(results, qvals):
        r.append(qv)
        r.append(r[5] > base_rate and r[10] < 0.10)   # beats (raw, legacy bar)
        r.append(r[5] > base_rate and qv < FDR_ALPHA)  # beats_fdr (rv2 bar)
    for (rid, rver, human, n, wins, win, avg, med, maxdd, expct, p, test_name,
         ci_lo, ci_hi, orat, abs_lift, rel_lift, power, qv, beats, beats_fdr) in results:
        verdict = "YES\u2020" if beats_fdr else ("yes*" if beats else "no")
        print(f"{rid:20} {n:>4} {win*100:>5.1f}% [{ci_lo*100:>4.1f},{ci_hi*100:>5.1f}] {orat:>6.2f} {abs_lift*100:>+5.1f} {med:>5.1f}% {expct:>6.1f}% {p:>7.3f} {qv:>7.3f} {power:>5.2f}  {verdict}")
    print("verdicts: YES\u2020 = beats after BH-FDR (q<%.2f) \u00b7 yes* = raw p<0.10 only (does NOT survive correction) \u00b7 lift = abs pp vs baseline" % FDR_ALPHA)

    if a.store and results:
        cur2 = conn.cursor()
        for (rid, rver, human, n, wins, win, avg, med, maxdd, expct, p, test_name,
             ci_lo, ci_hi, orat, abs_lift, rel_lift, power, qv, beats, beats_fdr) in results:
            cur2.execute("""INSERT INTO rule_validation_results
                (rule_id, rule_version, backtest_version, dataset, sql_filter, rule_filter,
                 date_range, n, win_rate, avg_return, median_return, max_drawdown,
                 expectancy, p_vs_baseline, beats_baseline, baseline_win_rate, universe_n, run_at,
                 ci95_low, ci95_high, odds_ratio, abs_lift, rel_lift, test_name,
                 q_bh, beats_fdr, power, git_hash, exclusion_ledger, finding_status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (rid, rver, BACKTEST_VERSION, DATASET, ELIG, human, date_range,
                 n, win, avg, med, maxdd, expct, p, beats, base_rate, n_all, ts,
                 ci_lo, ci_hi, orat, abs_lift, rel_lift, test_name,
                 qv, beats_fdr, power, ghash, json.dumps(ledger), FINDING_STATUS))
        conn.commit()
        print(f"STORED {len(results)} rows -> rule_validation_results ({BACKTEST_VERSION})")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
