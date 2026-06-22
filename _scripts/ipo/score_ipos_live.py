#!/usr/bin/env python3
"""
_scripts/ipo/score_ipos_live.py
─────────────────────────────────────────────────────────────────────────────
Applies the SAME scoring function that the backtest validated (score_ipo from
backtest_thesis.py) to every row in ipo_intelligence and writes the result back
to the play_* columns the UI reads.

This replaces the generic engine that was giving you nil/AVOID. After it runs,
the Command tab and Quick-Profit playbook show the logic that correctly called
Premier / Bajaj / Waaree as BUY_AT_OPEN and Afcons / ACME as AVOID.

Pipeline: fetch_nse_ipos.py (live rows + dates) -> score_ipos_live.py (this)
          -> Neon -> UI. Single source of truth for scoring is score_ipo();
          tune the thesis once, in backtest_thesis.py, and both stay in sync.

Usage:
  python _scripts/ipo/score_ipos_live.py            # score all, write
  python _scripts/ipo/score_ipos_live.py --dry-run  # print, write nothing
  python _scripts/ipo/score_ipos_live.py --recent 60

Install: pip install psycopg2-binary python-dotenv
"""

import os
import sys
import json
import argparse
import datetime
import logging
from pathlib import Path

# make sibling backtest_thesis importable regardless of CWD
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from dotenv import load_dotenv
    load_dotenv(".env.local" if Path(".env.local").exists() else ".env")
except ImportError:
    pass

import psycopg2
import psycopg2.extras
from backtest_thesis import score_ipo   # the validated thesis scorer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("score_ipos_live")

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print, write nothing")
    ap.add_argument("--recent", type=int, default=0,
                    help="only score rows listed/updated in last N days (0 = all)")
    args = ap.parse_args()

    if not DATABASE_URL:
        log.error("DATABASE_URL not set"); sys.exit(1)

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    where = "WHERE 1=1"
    if args.recent:
        cutoff = (datetime.date.today() - datetime.timedelta(days=args.recent)).isoformat()
        where += f" AND (listing_date >= '{cutoff}' OR listing_date IS NULL)"

    cur.execute(f"SELECT * FROM ipo_intelligence {where}")
    rows = cur.fetchall()
    log.info("Scoring %d IPOs", len(rows))

    counts, ok = {}, 0
    for row in rows:
        d = dict(row)
        rec, conf, score, reasons = score_ipo(d)
        counts[rec] = counts.get(rec, 0) + 1
        if args.dry_run:
            log.info("  %-38s %-14s %3d  %s", str(d.get("company_name"))[:38],
                     rec, conf, "; ".join(reasons[:3]))
            continue
        with conn.cursor() as uc:
            uc.execute("""
                UPDATE ipo_intelligence SET
                    play_recommendation = %s,
                    play_confidence     = %s,
                    play_reasons        = %s,
                    play_updated_at     = NOW()
                WHERE id = %s
            """, (rec, conf, json.dumps(reasons), d["id"]))
        ok += 1
        if ok % 50 == 0:
            conn.commit()

    if not args.dry_run:
        conn.commit()
        log.info("Updated %d IPOs", ok)
    conn.close()

    log.info("Recommendation distribution:")
    for rec, n in sorted(counts.items(), key=lambda x: -x[1]):
        log.info("  %-16s %d", rec, n)


if __name__ == "__main__":
    main()
