#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""compute_quality_score.py — the pre-listing Quality Score (0-100), v1 weights.

THE mission metric: fundamentally-strong vs junk, BEFORE listing, from data we
already hold. Factor definitions live in ONE place — backtest_quality_score.py
— and are imported here so the backtest and production can never drift.

v1 = SPEC candidate weights (docs/specifications/QUALITY_SCORE_SPEC.md). Calibration: run
backtest_quality_score.py, review the table, adjust THERE; this script inherits.
Writes ipo_intelligence.quality_score / quality_conf (additive columns).
Run:  python _scripts/compute_quality_score.py --apply    (no flag = preview)
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.quality_factors import factors  # ONE production-owned factor definition

import psycopg2

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    conn = psycopg2.connect(os.environ["DATABASE_URL"]); cur = conn.cursor()
    cur.execute("ALTER TABLE ipo_intelligence ADD COLUMN IF NOT EXISTS quality_score INT")
    cur.execute("ALTER TABLE ipo_intelligence ADD COLUMN IF NOT EXISTS quality_conf INT")
    cur.execute("""
      SELECT i.id, ri.full_json, v.quality_promoter, i.promoter_pledge_pct,
             i.ofs_cr, i.fresh_issue_cr, i.ipo_pe, i.peer_median_pe,
             i.roe, i.revenue_cagr_3y, i.debt_equity, i.sbi_rating, i.brlm_names
      FROM ipo_intelligence i
      LEFT JOIN ipo_rhp_intel ri ON ri.company_name = i.company_name
      LEFT JOIN ipo_verdicts v  ON v.company_name  = i.company_name""")
    rows = cur.fetchall()
    n_scored = 0
    for r in rows:
        f, score, conf = factors(tuple(r[1:]))
        if score is None or conf < 25:      # too little data to claim anything
            continue
        n_scored += 1
        if a.apply:
            cur.execute("UPDATE ipo_intelligence SET quality_score=%s, quality_conf=%s WHERE id=%s",
                        (score, conf, r[0]))
    if a.apply:
        conn.commit(); print(f"COMMITTED: quality_score on {n_scored}/{len(rows)} rows")
    else:
        conn.rollback(); print(f"preview: would score {n_scored}/{len(rows)} rows — rerun with --apply")

    # COVERAGE-FLOOR ALARM (permanent guard, 2026-07-18): the dial died three
    # times because coverage silently dropped. Now a drop SCREAMS. Floor scales
    # with data: after a backfill (more rows) the floor rises via the % gate,
    # so this passes when coverage GROWS and fails only on a real regression.
    total = len(rows)
    floor_pct = 0.60          # expect >=60% of rows scorable (today: 590/759 = 78%)
    if a.apply and total > 50 and n_scored < total * floor_pct:
        msg = (f"quality_score COVERAGE DROP: only {n_scored}/{total} "
               f"({100*n_scored//total}%) scored, floor {int(floor_pct*100)}%. "
               f"An upstream source (RHP db_fields / IPOMatrix fundamentals) "
               f"likely broke — dial will thin out.")
        try:
            cur2 = conn.cursor()
            cur2.execute("INSERT INTO pipeline_failures (step, script, stderr_tail) "
                         "VALUES ('quality score coverage','compute_quality_score.py',%s)", (msg[:490],))
            conn.commit()
        except Exception: pass
        print("!! " + msg)
    conn.close()

if __name__ == "__main__":
    main()
