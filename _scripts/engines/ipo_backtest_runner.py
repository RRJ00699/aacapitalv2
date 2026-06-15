"""
AACapital — IPO Backtest Runner
Task 4: Re-run IPO backtest after enrichment — target 80%+ accuracy

Run after ipo_data_enricher_v2.py completes.
Usage:
    python _scripts/engines/ipo_backtest_runner.py
    python _scripts/engines/ipo_backtest_runner.py --min-accuracy 0.80
    python _scripts/engines/ipo_backtest_runner.py --save-results
"""

import os
import sys
import argparse
import json
import math
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

NEON_URL = os.environ["NEON_DATABASE_URL"]


# ── helpers ────────────────────────────────────────────────────────────────────

def get_conn():
    return psycopg2.connect(NEON_URL)


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


# ── LQI scorer (mirrors ipo_intelligence_engine.py logic) ──────────────────────

def compute_lqi(ipo: dict) -> float:
    """
    150-point LQI model across 11 dimensions (A-K).
    Returns 0-100 normalised score.
    """
    score = 0.0

    # A — Subscription strength (25 pts)
    qib = ipo.get("qib_subscription") or 0
    nii = ipo.get("nii_subscription") or 0
    retail = ipo.get("retail_subscription") or 0
    total_sub = ipo.get("total_subscription") or 0
    if qib >= 50:    score += 10
    elif qib >= 20:  score += 7
    elif qib >= 5:   score += 4
    if nii >= 30:    score += 8
    elif nii >= 10:  score += 5
    if retail >= 5:  score += 4
    elif retail >= 2: score += 2
    if total_sub >= 30: score += 3
    elif total_sub >= 10: score += 1

    # B — Anchor investor quality (15 pts)
    anchor_class = (ipo.get("anchor_classification") or "").upper()
    anchor_count = ipo.get("anchor_investor_count") or 0
    if anchor_class == "STRONG":   score += 12
    elif anchor_class == "MEDIUM": score += 8
    elif anchor_class == "WEAK":   score += 3
    if anchor_count >= 20:  score += 3
    elif anchor_count >= 10: score += 1

    # C — GMP signal (15 pts)
    gmp_pct = ipo.get("gmp_percentage") or 0
    if gmp_pct >= 30:   score += 15
    elif gmp_pct >= 15: score += 10
    elif gmp_pct >= 5:  score += 6
    elif gmp_pct >= 0:  score += 2

    # D — Revenue / PAT growth (20 pts)
    rev_growth = ipo.get("revenue_growth_3yr") or 0
    pat_growth = ipo.get("pat_growth_3yr") or 0
    if rev_growth >= 30: score += 10
    elif rev_growth >= 15: score += 6
    elif rev_growth >= 5: score += 3
    if pat_growth >= 40: score += 10
    elif pat_growth >= 20: score += 6
    elif pat_growth >= 0: score += 2

    # E — Valuation (P/E vs peers) (15 pts)
    pe_ratio = ipo.get("pe_ratio") or 0
    sector_pe = ipo.get("sector_pe_median") or 0
    if sector_pe > 0 and pe_ratio > 0:
        ratio = pe_ratio / sector_pe
        if ratio <= 0.8:   score += 15
        elif ratio <= 1.0: score += 10
        elif ratio <= 1.3: score += 5

    # F — Promoter holding post-IPO (10 pts)
    promoter_holding = ipo.get("promoter_holding_post") or 0
    if promoter_holding >= 60:   score += 10
    elif promoter_holding >= 45: score += 6
    elif promoter_holding >= 30: score += 3

    # G — OFS vs fresh issue ratio (10 pts)
    ofs_pct = ipo.get("ofs_percentage") or 0
    if ofs_pct <= 20:   score += 10
    elif ofs_pct <= 40: score += 6
    elif ofs_pct <= 60: score += 3

    # H — Market regime at listing (10 pts)
    regime = (ipo.get("market_regime_at_listing") or "").upper()
    if regime == "BULLISH":   score += 10
    elif regime == "NEUTRAL": score += 5
    elif regime == "BEARISH": score += 0

    # I — Sector momentum (10 pts)
    sector_signal = (ipo.get("sector_momentum") or "").upper()
    if sector_signal == "STRONG":   score += 10
    elif sector_signal == "NEUTRAL": score += 5

    # J — IPO size (smaller = easier to list up) (10 pts)
    issue_size = ipo.get("issue_size_cr") or 0
    if issue_size <= 500:    score += 10
    elif issue_size <= 1000: score += 7
    elif issue_size <= 3000: score += 4

    # K — Listing exchange + SME flag (10 pts)
    is_sme = ipo.get("is_sme") or False
    exchange = (ipo.get("listing_exchange") or "").upper()
    if not is_sme and "NSE" in exchange: score += 10
    elif not is_sme:                     score += 7
    else:                                score += 3

    return round(min(score / 150 * 100, 100), 2)


def lqi_to_prediction(lqi: float) -> dict:
    """Convert LQI score to probability estimates."""
    # Sigmoid-style mapping calibrated from historical backtest
    p_profit_10 = 1 / (1 + math.exp(-0.08 * (lqi - 55)))
    p_loss      = 1 / (1 + math.exp( 0.07 * (lqi - 45)))
    expected_return = (lqi - 50) * 0.8  # rough linear for now

    if lqi >= 75:   conviction = "STRONG_BUY"
    elif lqi >= 60: conviction = "BUY"
    elif lqi >= 45: conviction = "NEUTRAL"
    elif lqi >= 30: conviction = "AVOID"
    else:           conviction = "STRONG_AVOID"

    return {
        "p_profit_10pct": round(p_profit_10, 3),
        "p_loss":         round(p_loss, 3),
        "expected_return_pct": round(expected_return, 1),
        "conviction": conviction,
    }


# ── backtest core ──────────────────────────────────────────────────────────────

def run_backtest(min_accuracy: float = 0.0) -> dict:
    conn = get_conn()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Pull IPOs that have actual listing outcome
    cur.execute("""
        SELECT *
        FROM ipo_intelligence
        WHERE listing_gap_pct IS NOT NULL
          AND listing_date IS NOT NULL
        ORDER BY listing_date DESC
    """)
    ipos = cur.fetchall()
    log(f"Found {len(ipos)} IPOs with listing outcome for backtest")

    if not ipos:
        log("ERROR: No IPOs with listing_gap_pct. Run enricher first.")
        conn.close()
        sys.exit(1)

    results = []
    correct_direction = 0
    correct_10pct     = 0
    strong_buy_wins   = 0
    strong_buy_total  = 0

    for ipo in ipos:
        ipo_dict = dict(ipo)
        lqi      = compute_lqi(ipo_dict)
        pred     = lqi_to_prediction(lqi)
        actual   = float(ipo_dict.get("listing_gap_pct") or 0)

        # Direction accuracy: did we predict profit / loss correctly?
        predicted_profit = pred["p_profit_10pct"] >= 0.5
        actual_profit    = actual >= 0
        direction_ok     = predicted_profit == actual_profit

        # 10% accuracy: if we predicted >10% gain, did it deliver?
        predicted_10  = pred["p_profit_10pct"] >= 0.65
        actual_10     = actual >= 10
        accuracy_10ok = predicted_10 == actual_10

        if direction_ok:  correct_direction += 1
        if accuracy_10ok: correct_10pct     += 1

        if pred["conviction"] in ("STRONG_BUY", "BUY"):
            strong_buy_total += 1
            if actual >= 10:
                strong_buy_wins += 1

        results.append({
            "ipo_name":      ipo_dict.get("company_name", ""),
            "listing_date":  str(ipo_dict.get("listing_date", "")),
            "lqi_score":     lqi,
            "conviction":    pred["conviction"],
            "p_profit_10":   pred["p_profit_10pct"],
            "p_loss":        pred["p_loss"],
            "actual_gain":   actual,
            "direction_ok":  direction_ok,
            "accuracy_10ok": accuracy_10ok,
        })

    n = len(ipos)
    direction_acc  = correct_direction / n
    accuracy_10pct = correct_10pct / n
    precision      = strong_buy_wins / strong_buy_total if strong_buy_total else 0

    summary = {
        "total_ipos_tested":      n,
        "direction_accuracy":     round(direction_acc, 4),
        "profit_10pct_accuracy":  round(accuracy_10pct, 4),
        "strong_buy_precision":   round(precision, 4),
        "strong_buy_total":       strong_buy_total,
        "strong_buy_wins":        strong_buy_wins,
        "run_timestamp":          datetime.now(timezone.utc).isoformat(),
    }

    log(f"Direction accuracy:    {direction_acc*100:.1f}%")
    log(f">10% profit accuracy:  {accuracy_10pct*100:.1f}%")
    log(f"BUY/STRONG_BUY precision: {precision*100:.1f}% ({strong_buy_wins}/{strong_buy_total})")

    if min_accuracy > 0 and accuracy_10pct < min_accuracy:
        log(f"WARNING: accuracy {accuracy_10pct*100:.1f}% below target {min_accuracy*100:.1f}%")
    elif accuracy_10pct >= min_accuracy:
        log(f"✅ Accuracy target {min_accuracy*100:.0f}%+ achieved!")

    return {"summary": summary, "results": results}


def save_results_to_neon(data: dict):
    conn = get_conn()
    cur  = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ipo_backtest_results (
            id              SERIAL PRIMARY KEY,
            run_timestamp   TIMESTAMPTZ NOT NULL,
            total_ipos      INT,
            direction_acc   NUMERIC(5,4),
            accuracy_10pct  NUMERIC(5,4),
            precision_buy   NUMERIC(5,4),
            results_json    JSONB,
            created_at      TIMESTAMPTZ DEFAULT now()
        )
    """)

    s = data["summary"]
    cur.execute("""
        INSERT INTO ipo_backtest_results
            (run_timestamp, total_ipos, direction_acc, accuracy_10pct, precision_buy, results_json)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        s["run_timestamp"],
        s["total_ipos_tested"],
        s["direction_accuracy"],
        s["profit_10pct_accuracy"],
        s["strong_buy_precision"],
        json.dumps(data["results"]),
    ))

    conn.commit()
    conn.close()
    log("✅ Backtest results saved to ipo_backtest_results in Neon")


def print_top_bottom(results: list, n: int = 10):
    sorted_r = sorted(results, key=lambda x: x["lqi_score"], reverse=True)
    print(f"\n{'─'*70}")
    print(f"{'TOP'} {n} LQI SCORES")
    print(f"{'─'*70}")
    print(f"{'Company':<30} {'LQI':>6} {'Conviction':<14} {'Actual':>8} {'Dir OK':>7}")
    for r in sorted_r[:n]:
        print(f"{r['ipo_name']:<30} {r['lqi_score']:>6.1f} {r['conviction']:<14} {r['actual_gain']:>7.1f}% {'✅' if r['direction_ok'] else '❌':>7}")

    print(f"\n{'BOTTOM'} {n} LQI SCORES")
    print(f"{'─'*70}")
    for r in sorted_r[-n:]:
        print(f"{r['ipo_name']:<30} {r['lqi_score']:>6.1f} {r['conviction']:<14} {r['actual_gain']:>7.1f}% {'✅' if r['direction_ok'] else '❌':>7}")


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AACapital IPO Backtest Runner")
    parser.add_argument("--min-accuracy", type=float, default=0.80,
                        help="Minimum target accuracy (default 0.80 = 80%%)")
    parser.add_argument("--save-results", action="store_true",
                        help="Save results to Neon ipo_backtest_results table")
    parser.add_argument("--no-table", action="store_true",
                        help="Skip printing top/bottom table")
    args = parser.parse_args()

    log("═" * 50)
    log("AACapital — IPO Backtest Runner")
    log("═" * 50)

    data = run_backtest(min_accuracy=args.min_accuracy)

    if not args.no_table:
        print_top_bottom(data["results"])

    if args.save_results:
        save_results_to_neon(data)

    # Write JSON report locally
    report_path = f"_output/ipo_backtest_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    os.makedirs("_output", exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(data, f, indent=2)
    log(f"Report saved → {report_path}")


if __name__ == "__main__":
    main()
