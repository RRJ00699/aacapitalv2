#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""backtest_quality_score.py — evidence table for the Quality Score spec.
Computes SPEC v1 candidate factors on every historical IPO with outcomes and
prints win-rate/mean-d10 per factor and per band. READ-ONLY. Run on PC:
    python research/backtests/backtest_quality_score.py
"""
import json, os
import psycopg2

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_scripts"))
from lib.quality_factors import factors, fnum

def main():
    conn = psycopg2.connect(os.environ["DATABASE_URL"]); cur = conn.cursor()
    # Every column below verified against live schema (2026-07-16 column dump +
    # ipo-command route): quality_promoter lives on ipo_verdicts (v.), NOT
    # intelligence — the first run of this script crashed guessing otherwise.
    cur.execute("""
      SELECT ri.full_json, v.quality_promoter, i.promoter_pledge_pct,
             i.ofs_cr, i.fresh_issue_cr, i.ipo_pe, i.peer_median_pe,
             i.roe, i.revenue_cagr_3y, i.debt_equity, i.sbi_rating, i.brlm_names,
             i.return_listing_open, i.d10_best_pct
      FROM ipo_intelligence i
      LEFT JOIN ipo_rhp_intel ri ON ri.company_name = i.company_name
      LEFT JOIN ipo_verdicts v  ON v.company_name  = i.company_name
      WHERE i.return_listing_open IS NOT NULL""")
    rows = cur.fetchall(); conn.close()
    print(f"historical IPOs with outcomes: {len(rows)}")
    factab, bands = {}, {}
    for r in rows:
        f, score, conf = factors(r[:12])
        ret_open, d10 = fnum(r[12]), fnum(r[13])
        if ret_open is None: continue
        win = ret_open > 0
        for k, v in f.items():
            if v is None: continue
            hit = v > 0
            key = (k, hit)
            a = factab.setdefault(key, [0, 0, 0.0, 0])
            a[0] += 1; a[1] += 1 if win else 0
            if d10 is not None: a[2] += d10; a[3] += 1
        if score is not None and conf >= 40:
            b = "STRONG" if score >= 75 else "SOLID" if score >= 55 else "MIXED" if score >= 35 else "WEAK"
            a = bands.setdefault(b, [0, 0, 0.0, 0])
            a[0] += 1; a[1] += 1 if win else 0
            if d10 is not None: a[2] += d10; a[3] += 1
    print(f"\n{'factor':<20}{'state':<6}{'n':>5}{'win%':>7}{'mean_d10':>10}")
    for (k, hit), (n, w, dsum, dn) in sorted(factab.items()):
        print(f"{k:<20}{'PASS' if hit else 'fail':<6}{n:>5}{w/n*100:>6.1f}%{(dsum/dn if dn else 0):>9.1f}%")
    print(f"\n{'band':<8}{'n':>5}{'win%':>7}{'mean_d10':>10}   (conf>=40 only)")
    for b in ("STRONG","SOLID","MIXED","WEAK"):
        if b in bands:
            n, w, dsum, dn = bands[b]
            print(f"{b:<8}{n:>5}{w/n*100:>6.1f}%{(dsum/dn if dn else 0):>9.1f}%")
    print("\nNext: review with Rakesh -> adjust weights -> LOCK -> compute step + dial.")

if __name__ == "__main__":
    main()
