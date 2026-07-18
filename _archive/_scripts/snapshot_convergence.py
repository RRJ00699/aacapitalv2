#!/usr/bin/env python3
"""
snapshot_convergence.py — append today's convergence scores to a DATED history table.

WHY: convergence_ranking is rebuilt fresh each run (only today's snapshot), and the
business/earnings factors come from current-only stock_fundamentals. So convergence
CANNOT be backtested retroactively — using today's quality scores on a past entry is
look-ahead bias that would fake a positive result.

This fixes that going forward: each daily run appends a dated row per stock. After a few
quarters you'll have real point-in-time history, and convergence becomes honestly testable
against forward returns (run a backtest then, not now).

Run it AFTER compute_convergence_ranking in the daily workflow.
Run:  python _scripts/snapshot_convergence.py
Env:  DATABASE_URL (or NEON_DATABASE_URL)
"""
import os, sys, psycopg2

URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
if not URL:
    sys.exit("DATABASE_URL not set")


def main():
    conn = psycopg2.connect(URL); conn.autocommit = True
    cur = conn.cursor()

    # is there anything to snapshot?
    cur.execute("""
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='public' AND table_name='convergence_ranking'
    """)
    if not cur.fetchone():
        sys.exit("convergence_ranking not found — run compute_convergence_ranking first")

    # Trading-day guard — only snapshot when today actually has a fresh candle.
    # Weekends and market holidays still trigger the daily Action, but no new candle is
    # written, so the technical factor floors out. Snapshotting CURRENT_DATE would then
    # stamp those junk scores into the point-in-time history (the backbone of the
    # "what changed" + future backtests). Require a candle dated today, else skip cleanly.
    # This also drops the redundant pre-open snapshot (today's candle doesn't exist yet at
    # 08:15) — the meaningful snapshot is the post-close run, which this preserves.
    cur.execute("SELECT MAX(date), CURRENT_DATE FROM price_candles")
    maxd, today = cur.fetchone()
    if maxd is None or maxd < today:
        print(f"skip: latest price_candle is {maxd}, not today ({today}) — "
              f"non-trading day or pre-close; not snapshotting.")
        cur.close(); conn.close()
        return

    cur.execute("""
        CREATE TABLE IF NOT EXISTS convergence_history (
            run_date    DATE NOT NULL,
            nse_symbol  TEXT NOT NULL,
            convergence NUMERIC,
            business    NUMERIC,
            earnings    NUMERIC,
            technical   NUMERIC,
            smart_money NUMERIC,
            sector      NUMERIC,
            action      TEXT,
            PRIMARY KEY (run_date, nse_symbol)
        )
    """)

    # copy today's snapshot in, idempotent for re-runs on the same day.
    # SELECT * + defensive column pick so it works whatever the exact column names are.
    cur.execute("SELECT * FROM convergence_ranking LIMIT 0")
    cols = [d[0] for d in cur.description]

    def pick(*cands):
        for c in cands:
            if c in cols:
                return c
        return "NULL"

    sym = pick("nse_symbol", "symbol")
    sel = ", ".join([
        "CURRENT_DATE",
        sym,
        pick("convergence", "convergence_score", "score"),
        pick("business", "business_score"),
        pick("earnings", "earnings_score"),
        pick("technical", "technical_score", "tech"),
        pick("smart_money", "smart_money_score", "sm"),
        pick("sector", "sector_score"),
        pick("action", "action_label"),
    ])
    cur.execute(f"""
        INSERT INTO convergence_history
          (run_date, nse_symbol, convergence, business, earnings, technical, smart_money, sector, action)
        SELECT {sel} FROM convergence_ranking
        WHERE {sym} IS NOT NULL
        ON CONFLICT (run_date, nse_symbol) DO UPDATE SET
          convergence = EXCLUDED.convergence, business = EXCLUDED.business,
          earnings = EXCLUDED.earnings, technical = EXCLUDED.technical,
          smart_money = EXCLUDED.smart_money, sector = EXCLUDED.sector, action = EXCLUDED.action
    """)

    cur.execute("SELECT COUNT(*) FROM convergence_history WHERE run_date = CURRENT_DATE")
    today = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT run_date) FROM convergence_history")
    days = cur.fetchone()[0]
    print(f"convergence_history: snapshotted {today:,} stocks for today; {days} distinct day(s) stored")
    print("Backtestable once you have several months of dated rows — not before.")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
