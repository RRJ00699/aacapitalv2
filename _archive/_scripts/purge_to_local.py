"""
_scripts/purge_to_local.py
============================
Archives old data from Neon → local Postgres. Never deletes from Neon.
Run on Windows (where LOCAL_DATABASE_URL points to local Postgres).
Run on Sundays when markets are closed and no data is being written.

Handover design rule: "Never delete — always archive to local postgres"

What gets archived:
  price_candles            > 2 years old
  management_commentary    > 2 years old (if table exists)

Usage:
  python _scripts/purge_to_local.py --dry-run     # see what would move
  python _scripts/purge_to_local.py               # archive it
  python _scripts/purge_to_local.py --table price_candles   # one table only
"""

import os, sys, logging, argparse, datetime
import psycopg2, psycopg2.extras
from urllib.parse import urlparse, unquote

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

NEON_URL  = os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")
LOCAL_URL = (os.getenv("LOCAL_DATABASE_URL")
             or os.getenv("CANDLES_DATABASE_URL")
             or "postgresql://postgres:Ashrith%402820@localhost:5432/aacapital?sslmode=disable")

CUTOFF_YEARS = 2   # archive data older than this


def safe_connect(url: str):
    """Parse URL properly — handles passwords containing @ encoded as %40."""
    p   = urlparse(url)
    qs  = dict(pair.split("=", 1) for pair in (p.query or "").split("&") if "=" in pair)
    kw  = dict(
        host     = p.hostname,
        port     = p.port or 5432,
        dbname   = p.path.lstrip("/"),
        user     = unquote(p.username or ""),
        password = unquote(p.password or ""),
    )
    if "sslmode" in qs:
        kw["sslmode"] = qs["sslmode"]
    return psycopg2.connect(**kw)


def cutoff_date() -> datetime.date:
    return (datetime.date.today() - datetime.timedelta(days=CUTOFF_YEARS * 365))


def archive_price_candles(neon, local, dry_run: bool) -> int:
    cut = cutoff_date()
    log.info(f"price_candles: archiving rows with date < {cut}")

    # Count
    cur = neon.cursor()
    cur.execute("SELECT COUNT(*) FROM price_candles WHERE date < %s", (cut,))
    total = cur.fetchone()[0]
    log.info(f"  Neon rows to archive: {total:,}")
    if total == 0:
        log.info("  Nothing to archive.")
        return 0
    if dry_run:
        log.info(f"  [dry-run] Would archive {total:,} rows")
        return total

    # Ensure local table exists
    lcur = local.cursor()
    lcur.execute("""
        CREATE TABLE IF NOT EXISTS price_candles (
            id       BIGSERIAL PRIMARY KEY,
            symbol   TEXT    NOT NULL,
            date     DATE    NOT NULL,
            open     NUMERIC(12,4),
            high     NUMERIC(12,4),
            low      NUMERIC(12,4),
            close    NUMERIC(12,4),
            volume   BIGINT,
            UNIQUE (symbol, date)
        )
    """)
    local.commit()

    # Paginate: fetch 10k rows at a time to avoid memory issues
    PAGE = 10_000
    moved = 0
    offset = 0
    while True:
        cur.execute("""
            SELECT symbol, date, open, high, low, close, volume
            FROM price_candles
            WHERE date < %s
            ORDER BY date, symbol
            LIMIT %s OFFSET %s
        """, (cut, PAGE, offset))
        rows = cur.fetchall()
        if not rows:
            break

        psycopg2.extras.execute_values(lcur, """
            INSERT INTO price_candles (symbol, date, open, high, low, close, volume)
            VALUES %s
            ON CONFLICT (symbol, date) DO NOTHING
        """, rows)
        local.commit()
        moved += len(rows)
        log.info(f"  Archived {moved:,} / {total:,} rows…")
        offset += PAGE

    cur.close()
    lcur.close()
    log.info(f"  ✅ {moved:,} rows archived to local price_candles")
    return moved


def archive_management_commentary(neon, local, dry_run: bool) -> int:
    cut = cutoff_date()
    cur = neon.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM management_commentary WHERE created_at < %s", (cut,))
        total = cur.fetchone()[0]
    except Exception:
        log.info("management_commentary: table doesn't exist on Neon yet, skipping")
        return 0

    log.info(f"management_commentary: {total:,} rows older than {cut}")
    if total == 0 or dry_run:
        if dry_run and total > 0:
            log.info(f"  [dry-run] Would archive {total:,} rows")
        return total

    lcur = local.cursor()
    lcur.execute("""
        CREATE TABLE IF NOT EXISTS management_commentary (
            id                 SERIAL PRIMARY KEY,
            nse_symbol         TEXT NOT NULL,
            quarter            TEXT NOT NULL,
            management_tone    TEXT,
            sentiment_score    NUMERIC(5,2),
            mgmt_quality_score NUMERIC(5,2),
            data_source        TEXT,
            created_at         TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (nse_symbol, quarter)
        )
    """)
    local.commit()

    cur.execute("""
        SELECT nse_symbol, quarter, management_tone, sentiment_score, mgmt_quality_score,
               data_source, created_at
        FROM management_commentary
        WHERE created_at < %s
    """, (cut,))
    rows = cur.fetchall()

    psycopg2.extras.execute_values(lcur, """
        INSERT INTO management_commentary
            (nse_symbol, quarter, management_tone, sentiment_score, mgmt_quality_score, data_source, created_at)
        VALUES %s
        ON CONFLICT (nse_symbol, quarter) DO NOTHING
    """, rows)
    local.commit()
    cur.close(); lcur.close()
    log.info(f"  ✅ {len(rows)} rows archived to local management_commentary")
    return len(rows)


def neon_size_report(neon):
    cur = neon.cursor()
    try:
        cur.execute("""
            SELECT
                schemaname, tablename,
                pg_size_pretty(pg_total_relation_size(quote_ident(schemaname)||'.'||quote_ident(tablename))) AS size,
                pg_total_relation_size(quote_ident(schemaname)||'.'||quote_ident(tablename)) AS bytes
            FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY bytes DESC NULLS LAST
            LIMIT 15
        """)
        rows = cur.fetchall()
        log.info("\n  Neon table sizes (top 15):")
        for r in rows:
            log.info(f"    {r[1]:35} {r[2]}")
    except Exception as e:
        log.warning(f"  Could not get table sizes: {e}")
    finally:
        cur.close()


def main():
    global CUTOFF_YEARS   # must declare before any use of the variable
    ap = argparse.ArgumentParser(description="Archive old Neon data to local Postgres")
    ap.add_argument("--dry-run", action="store_true", help="Show what would be archived, don't write")
    ap.add_argument("--table",   choices=["price_candles", "management_commentary", "all"], default="all")
    ap.add_argument("--years",   type=int, default=CUTOFF_YEARS, help="Archive data older than N years")
    args = ap.parse_args()

    CUTOFF_YEARS = args.years

    if not NEON_URL:
        log.error("DATABASE_URL not set — load .env.local first")
        sys.exit(1)

    log.info(f"Purge plan: archive data older than {cutoff_date()} from Neon → local Postgres")
    if args.dry_run:
        log.info("DRY RUN — nothing will be written")

    log.info("Connecting…")
    neon  = safe_connect(NEON_URL)
    local = safe_connect(LOCAL_URL)
    log.info("  ✅ Both DBs connected\n")

    # Show current sizes
    neon_size_report(neon)
    print()

    total_moved = 0
    if args.table in ("price_candles", "all"):
        total_moved += archive_price_candles(neon, local, args.dry_run)
    if args.table in ("management_commentary", "all"):
        total_moved += archive_management_commentary(neon, local, args.dry_run)

    neon.close()
    local.close()

    if args.dry_run:
        log.info(f"\nDry run complete. Would archive {total_moved:,} total rows.")
        log.info("Run without --dry-run to execute.")
    else:
        log.info(f"\n✅ Done. Archived {total_moved:,} total rows to local Postgres.")
        log.info("Neon data is UNCHANGED — rows were copied, not deleted.")
        log.info("To actually free Neon space, manually DELETE the archived rows after verifying local.")


if __name__ == "__main__":
    main()
