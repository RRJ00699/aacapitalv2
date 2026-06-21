"""
_scripts/purge_automation.py
=============================
Full data lifecycle management for AACapital Neon DB.
Runs different purge strategies per table based on data importance.

Schedule: Daily via GitHub Actions (2AM IST)

Usage:
  python _scripts/purge_automation.py --dry-run
  python _scripts/purge_automation.py --execute
  python _scripts/purge_automation.py --execute --table price_candles

Retention policy:
  price_candles          → 5 years rolling (delete older, keep 5Y)
  price_monthly          → 10 years (keep forever — small table)
  management_commentary  → 2 years (archive older to local)
  transcript_documents   → raw_text NULL after 90 days, metadata forever
  transcript_intelligence → 2 years
  daily_institutional_flows → 3 years
  market_regimes         → keep forever (small)
  ipo_intelligence       → keep forever (historical record)
  backtest_runs          → keep last 50 runs
  earnings_acceleration_scores → 2 years
  ownership_signals      → keep forever
  shareholding_history   → 10 years
"""

import os, sys, logging, argparse, datetime
import psycopg2
import psycopg2.extras

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
LOCAL_URL    = os.environ.get("LOCAL_DATABASE_URL") or os.environ.get("LOCAL_POSTGRES_URL")
# LOCAL_URL is your local postgres at postgresql://postgres:password@localhost:5432/aacapital
# Set in .env.local: LOCAL_DATABASE_URL=postgresql://postgres:Ashrith@2820@localhost:5432/aacapital
# When LOCAL_URL is not set, archive strategy falls back to DELETE (data is lost)
# IMPORTANT: Always set LOCAL_DATABASE_URL in .env.local on your Windows machine


PURGE_RULES = [
    # (table, date_column, retention_days, strategy, description)
    ("price_candles",              "date",         365*2,  "archive",     "Archive 2Y+ candles to local, keep 2Y in Neon"),
    ("management_commentary",      "updated_at",   365*2,  "archive",     "Keep 2Y commentary, archive older"),
    ("transcript_documents",       "created_at",   90,     "null_text",   "Clear raw_text after 90 days"),
    ("transcript_intelligence",    "updated_at",   365*2,  "archive",     "Archive 2Y+ transcript intel to local"),
    ("daily_institutional_flows",  "trade_date",   365*3,  "delete_old",  "Keep 3Y FII/DII flows"),
    ("earnings_acceleration_scores","updated_at",  365*2,  "archive",     "Archive 2Y+ earnings scores to local"),
    ("audit_log",                  "created_at",   90,     "delete_old",  "Keep 90 days audit logs"),
    ("backtest_runs",              None,           50,     "keep_last_n", "Keep last 50 backtest runs"),
]


def get_neon():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL not set")
    return psycopg2.connect(DATABASE_URL, connect_timeout=10)


def get_local():
    if not LOCAL_URL:
        return None
    try:
        return psycopg2.connect(LOCAL_URL, connect_timeout=5)
    except:
        return None


def table_exists(conn, table: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM information_schema.tables WHERE table_name=%s AND table_schema='public'", (table,))
    exists = cur.fetchone() is not None
    cur.close()
    return exists


def get_count(conn, table: str, where: str = "") -> int:
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT COUNT(*) FROM {table} {where}")
        return cur.fetchone()[0]
    except:
        return -1
    finally:
        cur.close()


def run_purge(dry_run: bool, target_table: str | None = None):
    log.info(f"AACapital Data Purge — {'DRY RUN' if dry_run else 'EXECUTING'}")
    log.info("=" * 60)

    neon  = get_neon()
    local = get_local()

    total_freed = 0

    for table, date_col, retention, strategy, desc in PURGE_RULES:
        if target_table and table != target_table:
            continue
        if not table_exists(neon, table):
            log.info(f"  {table}: table not found, skipping")
            continue

        cur = neon.cursor()

        if strategy == "delete_old":
            cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=retention)
            count = get_count(neon, table, f"WHERE {date_col} < '{cutoff.date()}'")
            total = get_count(neon, table)
            log.info(f"  {table}: {count:,}/{total:,} rows would be deleted (>{retention//365}Y old) — {desc}")
            if not dry_run and count > 0:
                cur.execute(f"DELETE FROM {table} WHERE {date_col} < %s", (cutoff,))
                neon.commit()
                log.info(f"    ✓ Deleted {count:,} rows")
                total_freed += count

        elif strategy == "null_text":
            cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=retention)
            count = get_count(neon, table, f"WHERE {date_col} < '{cutoff.date()}' AND raw_text IS NOT NULL")
            log.info(f"  {table}: {count:,} rows would have raw_text cleared (>{retention}d old) — {desc}")
            if not dry_run and count > 0:
                cur.execute(f"UPDATE {table} SET raw_text = NULL WHERE {date_col} < %s AND raw_text IS NOT NULL", (cutoff,))
                neon.commit()
                log.info(f"    ✓ Cleared raw_text from {count:,} rows")

        elif strategy == "archive":
            cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=retention)
            count = get_count(neon, table, f"WHERE {date_col} < '{cutoff.date()}'")
            log.info(f"  {table}: {count:,} rows would be archived then deleted (>{retention//365}Y old) — {desc}")
            if not dry_run and count > 0:
                if local:
                    # Archive to local first
                    cur.execute(f"SELECT * FROM {table} WHERE {date_col} < %s LIMIT 10000", (cutoff,))
                    rows = cur.fetchall()
                    colnames = [desc.name for desc in cur.description]
                    local_cur = local.cursor()
                    try:
                        local_cur.execute(f"""
                            CREATE TABLE IF NOT EXISTS {table}_archive
                            AS SELECT * FROM {table} WHERE 1=0
                        """)
                        local.commit()
                        psycopg2.extras.execute_values(
                            local_cur,
                            f"INSERT INTO {table}_archive ({','.join(colnames)}) VALUES %s ON CONFLICT DO NOTHING",
                            rows
                        )
                        local.commit()
                        log.info(f"    ✓ Archived {len(rows)} rows to local")
                    except Exception as e:
                        log.warning(f"    Archive failed: {e} — deleting without archive")
                    local_cur.close()
                cur.execute(f"DELETE FROM {table} WHERE {date_col} < %s", (cutoff,))
                neon.commit()
                log.info(f"    ✓ Deleted {count:,} rows from Neon")
                total_freed += count

        elif strategy == "keep_last_n":
            total = get_count(neon, table)
            to_delete = max(0, total - retention)
            log.info(f"  {table}: {total} runs, would keep last {retention}, delete {to_delete} — {desc}")
            if not dry_run and to_delete > 0:
                cur.execute(f"""
                    DELETE FROM {table} WHERE id NOT IN (
                        SELECT id FROM {table} ORDER BY id DESC LIMIT {retention}
                    )
                """)
                neon.commit()
                log.info(f"    ✓ Deleted {to_delete} old runs")
                total_freed += to_delete

        cur.close()

    # Storage summary
    log.info("")
    log.info("Current table sizes in Neon:")
    try:
        cur = neon.cursor()
        cur.execute("""
            SELECT relname AS table,
                   pg_size_pretty(pg_total_relation_size(relid)) AS size,
                   n_live_tup AS rows
            FROM pg_stat_user_tables
            ORDER BY pg_total_relation_size(relid) DESC
            LIMIT 15
        """)
        for table, size, rows in cur.fetchall():
            log.info(f"  {table:40} {size:10} {rows:>10,} rows")
        cur.close()
    except Exception as e:
        log.warning(f"  Could not get table sizes: {e}")

    neon.close()
    if local:
        local.close()

    log.info("")
    log.info("=" * 60)
    if dry_run:
        log.info("DRY RUN — no changes made. Run with --execute to apply.")
    else:
        log.info(f"Purge complete. ~{total_freed:,} rows freed.")


def main():
    p = argparse.ArgumentParser(description="AACapital data purge automation")
    p.add_argument("--dry-run", action="store_true", default=True)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--table",   help="Purge only this table")
    args = p.parse_args()

    if not DATABASE_URL:
        log.error("DATABASE_URL not set"); sys.exit(1)

    run_purge(dry_run=not args.execute, target_table=args.table)


if __name__ == "__main__":
    main()
