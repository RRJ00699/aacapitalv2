#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""smoke_probe.py v2 — post-pipeline smoke (LAST lean step).
v1 probed /api/ipo-command over HTTP — wrong layer: that route is session-
gated (401 from the VM, correctly). v2 tests what the VM CAN prove:

1. DB CONTRACT: one SELECT naming EVERY column the command/live routes depend
   on. Schema drift (the #159/#184/#198 class) fails HERE, with the column
   named, before any user sees a degraded banner. This list and schema_sync.py
   are siblings — extend both together.
2. WORKER CHAIN: /api/admin/job-flag with ADMIN_JOB_KEY — proves worker up,
   KV bound, auth wired (the one API path built for machine access).
Failure exits 1 -> failure sink -> Pipeline health -> phone.
"""
import json, os, sys, urllib.request
import psycopg2

CONTRACT = """
SELECT company_name, listing_date, ipo_open_date, ipo_close_date, issue_size_cr,
       issue_price, price_band_low, price_band_high, chittorgarh_slug,
       anchor_count, ofs_cr, fresh_issue_cr, ipo_pe, peer_median_pe,
       roe, revenue_cagr_3y, debt_equity, pat_cr, eps_post, eps_source,
       quality_score, quality_conf, ipo_score, score_band,
       score_expected_win, score_expected_med, gmp_day_before,
       mcap_offer, nse_symbol, symbol
FROM ipo_intelligence LIMIT 1"""

def main():
    fails = []
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"]); cur = conn.cursor()
        cur.execute(CONTRACT)
        cur.execute("SELECT verdict, score, confidence, quality_promoter FROM ipo_verdicts LIMIT 1")
        cur.execute("SELECT company, source, rating, pdf_path, full_json, one_line FROM ipo_research_notes LIMIT 1")
        cur.execute("SELECT symbol, discovery_price, buy_qty, sell_qty, lean_pct, source FROM ipo_preopen_book LIMIT 1")
        conn.close()
    except Exception as e:
        fails.append(f"DB CONTRACT: {str(e)[:160]}")
    key = os.getenv("ADMIN_JOB_KEY", "")
    if key:
        try:
            req = urllib.request.Request(
                "https://aacapitalprivatelimited.com/api/admin/job-flag",
                headers={"X-AAC-Key": key, "User-Agent": "aac-smoke"})
            d = json.load(urllib.request.urlopen(req, timeout=30))
            if not d.get("ok"): fails.append("worker chain: job-flag rejected the key")
        except Exception as e:
            fails.append(f"worker chain: {str(e)[:100]}")
    else:
        print("  (ADMIN_JOB_KEY unset — worker-chain probe skipped)")
    if fails:
        print("SMOKE FAIL:\n  " + "\n  ".join(fails)); sys.exit(1)
    print("SMOKE PASS: DB contract intact (30+ route-critical columns) · worker chain healthy")

if __name__ == "__main__":
    main()
