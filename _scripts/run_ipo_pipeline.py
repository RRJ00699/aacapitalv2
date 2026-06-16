"""
AACapital — IPO Data Pipeline Master Runner
Run all 3 scrapers in correct sequence.

Usage:
    python _scripts/run_ipo_pipeline.py
    python _scripts/run_ipo_pipeline.py --step 1   # only chittorgarh
    python _scripts/run_ipo_pipeline.py --step 2   # only returns calculator
    python _scripts/run_ipo_pipeline.py --step 3   # only GMP
    python _scripts/run_ipo_pipeline.py --step 4   # only anchors
"""

import os
import sys
import time
import logging
import argparse
import subprocess
from datetime import datetime

LOG_FILE = "_scripts/logs/pipeline_run.log"
os.makedirs("_scripts/logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("pipeline")


STEPS = {
    1: {
        "name": "Chittorgarh Master Scraper",
        "script": "_scripts/scraper_chittorgarh.py",
        "fills": "issue_price, dates, BRLM, listing_price, listing_gain, subscription",
        "duration": "~60-90 min for 304 IPOs",
        "priority": "CRITICAL",
    },
    2: {
        "name": "Returns Calculator (Kite candles)",
        "script": "_scripts/calculator_returns.py",
        "fills": "return_day1/7/30/90, max_drawdown, winner_bucket",
        "duration": "~5-10 min (uses existing DB data)",
        "priority": "CRITICAL",
        "note": "Run this FIRST if you want quick wins — no scraping needed",
    },
    3: {
        "name": "GMP History Scraper",
        "script": "_scripts/scraper_gmp.py",
        "fills": "gmp_t1/3/5/7/10, gmp_velocity, gmp_momentum",
        "duration": "~45-60 min for 304 IPOs",
        "priority": "HIGH",
    },
    4: {
        "name": "Anchor Investor Scraper",
        "script": "_scripts/scraper_anchors.py",
        "fills": "anchor_quality, anchor_names, anchor_domestic_pct, flip_risk",
        "duration": "~30-45 min for 304 IPOs",
        "priority": "MEDIUM",
    },
}


def banner():
    log.info("\n" + "=" * 65)
    log.info("  AACapital — IPO Data Pipeline")
    log.info(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 65)
    log.info("\nWhat each step fills:")
    for step_num, s in STEPS.items():
        log.info(f"\n  Step {step_num}: {s['name']}  [{s['priority']}]")
        log.info(f"    Fills:    {s['fills']}")
        log.info(f"    Duration: {s['duration']}")
        if s.get("note"):
            log.info(f"    ⚡ {s['note']}")


def check_env():
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        log.error("\n✗ DATABASE_URL is not set!")
        log.error("  Set it with: $env:DATABASE_URL = 'postgresql://...'")
        log.error("  Or ensure .env.local is loaded.\n")
        return False

    xlsx = os.environ.get("IPO_EXCEL", "aacapital_ipo_master_304.xlsx")
    if not os.path.exists(xlsx):
        log.warning(f"  ⚠ IPO Excel not found at: {xlsx}")
        log.warning("  Set IPO_EXCEL env var to the correct path.")

    log.info(f"✓ DATABASE_URL set (ends with ...{db_url[-20:]})")
    return True


def run_step(step_num: int) -> bool:
    step = STEPS[step_num]
    script = step["script"]

    if not os.path.exists(script):
        log.error(f"Script not found: {script}")
        log.error(f"Copy the scripts to your _scripts/ folder first.")
        return False

    log.info(f"\n{'─' * 65}")
    log.info(f"STEP {step_num}: {step['name']}")
    log.info(f"{'─' * 65}")

    start = time.time()
    try:
        result = subprocess.run(
            [sys.executable, script],
            env=os.environ.copy(),
            check=False,
        )
        elapsed = round(time.time() - start, 1)

        if result.returncode == 0:
            log.info(f"\n✓ Step {step_num} completed in {elapsed}s")
            return True
        else:
            log.error(f"\n✗ Step {step_num} failed (exit code {result.returncode}) after {elapsed}s")
            return False
    except Exception as e:
        log.error(f"  Error running step {step_num}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="AACapital IPO Data Pipeline")
    parser.add_argument("--step", type=int, choices=[1, 2, 3, 4],
                        help="Run only a specific step")
    parser.add_argument("--skip-check", action="store_true",
                        help="Skip environment check")
    args = parser.parse_args()

    banner()

    if not args.skip_check and not check_env():
        sys.exit(1)

    if args.step:
        # Run single step
        success = run_step(args.step)
        sys.exit(0 if success else 1)
    else:
        # Run all steps in recommended order
        # Step 2 first: fastest, uses existing data
        order = [2, 1, 3, 4]
        results = {}

        for step_num in order:
            success = run_step(step_num)
            results[step_num] = "✓ OK" if success else "✗ FAILED"
            if not success:
                log.warning(f"  Step {step_num} failed. Continuing with next step …")

        # Summary
        log.info("\n" + "=" * 65)
        log.info("PIPELINE SUMMARY")
        log.info("=" * 65)
        for step_num in order:
            step = STEPS[step_num]
            log.info(f"  Step {step_num} ({step['name']}): {results[step_num]}")
        log.info(f"\nFinished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
