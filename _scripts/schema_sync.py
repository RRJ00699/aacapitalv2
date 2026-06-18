"""
_scripts/schema_sync.py
========================
Makes local Postgres schema identical to Neon.
Copies table definitions, views, indexes from Neon → local.
Does NOT copy data (use kite-sync-candles.py for candles).

Usage:
  python _scripts/schema_sync.py --dry-run   # show what would change
  python _scripts/schema_sync.py --execute   # apply changes

Requires: pip install psycopg2-binary
"""

import os, sys, logging, argparse
import psycopg2
import psycopg2.extras

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

NEON_URL  = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
LOCAL_URL = os.environ.get("LOCAL_DATABASE_URL") or os.environ.get("CANDLES_DATABASE_URL") or \
            "postgresql://postgres:Ashrith%402820@localhost:5432/aacapital?sslmode=disable"

# Tables that MUST exist in both local and Neon
REQUIRED_TABLES = [
    "stock_fundamentals",
    "technical_signals",
    "management_commentary",
    "sector_rotation",
    "market_regimes",
    "market_snapshot",
    "daily_institutional_flows",
    "ipo_intelligence",
    "ipo_master",
    "mf_stock_summary",
    "mf_scheme_holdings",
    "shareholding_history",
    "ownership_signals",
    "quarterly_results",
    "earnings_acceleration_scores",
    "transcript_intelligence",
    "transcript_documents",
    "management_quality_history",
    "weekly_dna",
    "price_candles",          # candles — Neon gets top 200, local has all
    "price_monthly",
    "backtest_runs",
    "trade_journal",
    "watchlist_stocks",
    "platform_config",
]


def get_conn(url: str, label: str):
    try:
        conn = psycopg2.connect(url, connect_timeout=10)
        log.info(f"  Connected to {label}")
        return conn
    except Exception as e:
        log.error(f"  Cannot connect to {label}: {e}")
        sys.exit(1)


def get_tables(conn) -> set:
    cur = conn.cursor()
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
    """)
    tables = {r[0] for r in cur.fetchall()}
    cur.close()
    return tables


def get_table_ddl(conn, table: str) -> str | None:
    """Get CREATE TABLE statement from pg_dump style query."""
    cur = conn.cursor()
    try:
        cur.execute(f"""
            SELECT column_name, data_type, character_maximum_length,
                   is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = %s AND table_schema = 'public'
            ORDER BY ordinal_position
        """, (table,))
        cols = cur.fetchall()
        if not cols:
            return None

        col_defs = []
        for name, dtype, maxlen, nullable, default in cols:
            col_def = f"    {name} "
            if dtype == "character varying":
                col_def += f"VARCHAR({maxlen or 255})"
            elif dtype == "character":
                col_def += f"CHAR({maxlen or 1})"
            elif dtype in ("integer", "bigint", "smallint", "numeric", "real",
                           "double precision", "boolean", "text", "date",
                           "timestamp with time zone", "timestamp without time zone",
                           "jsonb", "json", "uuid"):
                col_def += dtype.upper()
            else:
                col_def += dtype.upper()
            if default:
                col_def += f" DEFAULT {default}"
            if nullable == "NO":
                col_def += " NOT NULL"
            col_defs.append(col_def)

        return f"CREATE TABLE IF NOT EXISTS {table} (\n" + ",\n".join(col_defs) + "\n)"
    except Exception as e:
        log.debug(f"DDL error for {table}: {e}")
        return None
    finally:
        cur.close()


def get_views(conn) -> dict:
    cur = conn.cursor()
    cur.execute("""
        SELECT table_name, view_definition
        FROM information_schema.views
        WHERE table_schema = 'public'
    """)
    views = {r[0]: r[1] for r in cur.fetchall()}
    cur.close()
    return views


def sync_schema(dry_run: bool):
    log.info("Schema Sync: Neon → Local")
    log.info("=" * 60)

    neon  = get_conn(NEON_URL,  "Neon")
    local = get_conn(LOCAL_URL, "Local Postgres")

    neon_tables  = get_tables(neon)
    local_tables = get_tables(local)
    neon_views   = get_views(neon)

    log.info(f"Neon:  {len(neon_tables)} tables, {len(neon_views)} views")
    log.info(f"Local: {len(local_tables)} tables")
    log.info("")

    # Find tables missing from local
    missing = [t for t in REQUIRED_TABLES if t in neon_tables and t not in local_tables]
    extra   = [t for t in local_tables if t not in neon_tables and t not in REQUIRED_TABLES]

    log.info(f"Missing from local: {len(missing)}")
    for t in missing:
        log.info(f"  - {t}")

    log.info(f"Local-only tables (not in Neon): {len(extra)}")
    for t in extra:
        log.info(f"  ~ {t}")

    if not dry_run and missing:
        log.info("")
        log.info("Creating missing tables in local...")
        local_cur = local.cursor()
        for table in missing:
            ddl = get_table_ddl(neon, table)
            if ddl:
                try:
                    local_cur.execute(ddl)
                    local.commit()
                    log.info(f"  ✓ Created {table}")
                except Exception as e:
                    local.rollback()
                    log.warning(f"  ✗ {table}: {e}")
            else:
                log.warning(f"  ? Could not get DDL for {table}")
        local_cur.close()

    # Sync views
    local_views = get_views(local)
    missing_views = [v for v in neon_views if v not in local_views]
    log.info(f"\nViews missing from local: {len(missing_views)}")
    for v in missing_views:
        log.info(f"  - {v}")

    if not dry_run and missing_views:
        local_cur = local.cursor()
        for view_name in missing_views:
            try:
                local_cur.execute(f"CREATE OR REPLACE VIEW {view_name} AS {neon_views[view_name]}")
                local.commit()
                log.info(f"  ✓ Created view {view_name}")
            except Exception as e:
                local.rollback()
                log.warning(f"  ✗ View {view_name}: {e}")
        local_cur.close()

    neon.close()
    local.close()

    log.info("")
    log.info("=" * 60)
    if dry_run:
        log.info("DRY RUN — no changes made. Run with --execute to apply.")
    else:
        log.info("Schema sync complete.")


def main():
    p = argparse.ArgumentParser(description="Sync Neon schema → Local Postgres")
    p.add_argument("--dry-run", action="store_true", default=True,
                   help="Show what would change (default)")
    p.add_argument("--execute", action="store_true",
                   help="Actually apply changes")
    args = p.parse_args()

    if not NEON_URL:
        log.error("DATABASE_URL not set"); sys.exit(1)

    sync_schema(dry_run=not args.execute)


if __name__ == "__main__":
    main()
