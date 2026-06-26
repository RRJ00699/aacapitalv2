#!/usr/bin/env python3
"""
reconcile_universe.py — keep company_master a superset of the real universe.

The bug it closes: populate_company_master.py seeds company_master FROM price_candles,
and the daily sync fetches candles FROM company_master — a closed loop. Any stock added
to stock_fundamentals that wasn't already in the candle seed can never enter either, so
it silently never gets candles (this is how the entire Nifty large-cap core ended up with
zero history).

Fix: every run, insert any stock_fundamentals symbol (at/above a market-cap floor) that's
missing from company_master. After this, the daily candle sync picks them up automatically
on its next run — the gap can never silently reopen. Run it as a step in ipo-daily.yml
BEFORE the candle sync (see the README note below).

The floor keeps micro-cap SME junk out (mirrors the earlier decision to skip <1k cr). Set
UNIVERSE_MIN_MCAP=0 to include everything.

Run:  python _scripts/reconcile_universe.py
      python _scripts/reconcile_universe.py --dry-run
Env:  DATABASE_URL (Neon); UNIVERSE_MIN_MCAP (cr, default 1000)
"""
import os
import sys
import argparse
import logging
import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger()

URL   = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
FLOOR = float(os.environ.get("UNIVERSE_MIN_MCAP", "1000"))
if not URL:
    sys.exit("DATABASE_URL not set")

FIND_MISSING = """
    SELECT sf.nse_symbol, sf.name, sf.industry, sf.industry_group, sf.market_cap
    FROM stock_fundamentals sf
    LEFT JOIN company_master cm ON cm.symbol = sf.nse_symbol
    WHERE cm.symbol IS NULL
      AND sf.nse_symbol IS NOT NULL
      AND sf.market_cap >= %s
    ORDER BY sf.market_cap DESC NULLS LAST
"""

INSERT = """
    INSERT INTO company_master
        (symbol, nse_symbol, company_name, sector, industry_group, is_active, updated_at)
    VALUES (%s, %s, %s, %s, %s, TRUE, NOW())
    ON CONFLICT (symbol) DO NOTHING
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(URL)
    cur = conn.cursor()
    cur.execute(FIND_MISSING, (FLOOR,))
    rows = cur.fetchall()

    log.info(f"{len(rows)} stock_fundamentals symbols (>= {FLOOR:.0f} cr) are missing from company_master")
    for sym, name, _i, _ig, mcap in rows[:30]:
        log.info(f"   + {sym:14} {str(name)[:26]:26} {float(mcap or 0):,.0f} cr")
    if len(rows) > 30:
        log.info(f"   … and {len(rows)-30} more")

    if args.dry_run:
        log.info("Dry run — no writes.")
        conn.close(); return
    if not rows:
        log.info("company_master already covers the universe. Nothing to do.")
        conn.close(); return

    added = 0
    for sym, name, industry, industry_group, _m in rows:
        cur.execute(INSERT, (sym, sym, name, industry, industry_group))
        added += cur.rowcount
    conn.commit()
    conn.close()

    log.info(f"Added {added} symbols to company_master. The daily candle sync will fetch them on its next run.")
    log.info("For immediate ~10yr depth on the new entrants, run: python _scripts/deepen_candles_to_10yr.py")


if __name__ == "__main__":
    main()
