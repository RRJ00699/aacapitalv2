"""
_scripts/purge_management_commentary.py
========================================
Weekly maintenance for management_commentary and transcript_intelligence tables.

What it does:
  1. Archives rows older than 90 days from Neon → local Postgres (optional)
  2. Deletes rows older than 90 days from Neon
  3. Deletes transcript_documents raw_text older than 90 days (keeps metadata)
  4. Prints a storage summary

Usage:
  python _scripts/purge_management_commentary.py            # dry run - shows what would be deleted
  python _scripts/purge_management_commentary.py --execute  # actually deletes
  python _scripts/purge_management_commentary.py --execute --archive  # archive to local before deleting

Schedule: Weekly via GitHub Actions (Sundays 2AM IST)
"""

import os
import sys
import json
import logging
import argparse
import datetime
import psycopg2
import psycopg2.extras

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

DATABASE_URL    = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
LOCAL_DB_URL    = os.environ.get("LOCAL_DATABASE_URL") or os.environ.get("CANDLES_DATABASE_URL")
RETENTION_DAYS  = 90


def get_neon():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL not set")
    return psycopg2.connect(DATABASE_URL, connect_timeout=10)


def get_local():
    if not LOCAL_DB_URL:
        raise RuntimeError("LOCAL_DATABASE_URL not set")
    return psycopg2.connect(LOCAL_DB_URL, connect_timeout=5)


def ensure_archive_table(local_conn):
    """Create archive table in local Postgres if it doesn't exist."""
    cur = local_conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS management_commentary_archive (
            id                  INTEGER,
            nse_symbol          VARCHAR(20),
            company_name        TEXT,
            quarter             VARCHAR(10),
            revenue_guidance    TEXT,
            margin_guidance     TEXT,
            management_tone     VARCHAR(30),
            guidance_direction  VARCHAR(20),
            sentiment_score     NUMERIC,
            mgmt_quality_score  NUMERIC,
            confidence          VARCHAR(10),
            data_source         VARCHAR(30),
            key_growth_drivers  TEXT,
            key_risks           TEXT,
            created_at          TIMESTAMPTZ,
            archived_at         TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    local_conn.commit()
    cur.close()


def dry_run():
    """Show what would be deleted without doing anything."""
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=RETENTION_DAYS)
    neon   = get_neon()
    cur    = neon.cursor()

    log.info(f"DRY RUN — rows older than {RETENTION_DAYS} days ({cutoff.date()}) would be affected:")
    log.info("")

    tables = [
        ("management_commentary",   "updated_at"),
        ("transcript_intelligence", "updated_at"),
        ("transcript_documents",    "created_at"),
    ]

    for table, date_col in tables:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {date_col} < %s", (cutoff,))
            count = cur.fetchone()[0]
            cur.execute(f"SELECT COUNT(*) FROM {table}", ())
            total = cur.fetchone()[0]
            log.info(f"  {table:40} {count:5} / {total:5} rows would be deleted")
        except Exception as e:
            log.warning(f"  {table}: {e}")

    cur.close()
    neon.close()
    log.info("")
    log.info("Run with --execute to actually delete, --execute --archive to archive first.")


def archive_to_local(neon_cur, cutoff: datetime.datetime):
    """Copy old rows to local Postgres before deletion."""
    try:
        local = get_local()
        ensure_archive_table(local)
        local_cur = local.cursor()

        neon_cur.execute("""
            SELECT id, nse_symbol, company_name, quarter,
                   revenue_guidance, margin_guidance,
                   management_tone, guidance_direction,
                   sentiment_score, mgmt_quality_score, confidence, data_source,
                   key_growth_drivers::text, key_risks::text,
                   created_at
            FROM management_commentary
            WHERE updated_at < %s
        """, (cutoff,))

        rows = neon_cur.fetchall()
        if rows:
            psycopg2.extras.execute_values(
                local_cur,
                """INSERT INTO management_commentary_archive
                   (id, nse_symbol, company_name, quarter,
                    revenue_guidance, margin_guidance,
                    management_tone, guidance_direction,
                    sentiment_score, mgmt_quality_score, confidence, data_source,
                    key_growth_drivers, key_risks, created_at)
                   VALUES %s
                   ON CONFLICT DO NOTHING""",
                rows
            )
            local.commit()
            log.info(f"  Archived {len(rows)} rows to local Postgres")
        else:
            log.info("  No rows to archive")

        local_cur.close()
        local.close()

    except Exception as e:
        log.warning(f"  Archive to local failed (continuing with Neon purge): {e}")


def execute_purge(do_archive: bool):
    """Actually delete old rows from Neon."""
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=RETENTION_DAYS)
    neon   = get_neon()
    cur    = neon.cursor()

    log.info(f"EXECUTE — purging rows older than {RETENTION_DAYS} days ({cutoff.date()})")
    log.info("")

    # ── Archive first if requested ────────────────────────────────────────────
    if do_archive:
        log.info("Step 1: Archiving to local Postgres...")
        archive_to_local(cur, cutoff)
    else:
        log.info("Step 1: Skipping archive (use --archive to enable)")

    # ── Delete from management_commentary ─────────────────────────────────────
    log.info("Step 2: Purging management_commentary...")
    cur.execute("DELETE FROM management_commentary WHERE updated_at < %s RETURNING nse_symbol", (cutoff,))
    deleted_mc = cur.rowcount
    log.info(f"  Deleted {deleted_mc} rows from management_commentary")

    # ── Delete from transcript_intelligence ───────────────────────────────────
    log.info("Step 3: Purging transcript_intelligence...")
    cur.execute("DELETE FROM transcript_intelligence WHERE updated_at < %s RETURNING nse_symbol", (cutoff,))
    deleted_ti = cur.rowcount
    log.info(f"  Deleted {deleted_ti} rows from transcript_intelligence")

    # ── Nullify raw_text in transcript_documents (keep metadata) ─────────────
    log.info("Step 4: Clearing raw_text from old transcript_documents...")
    cur.execute("""
        UPDATE transcript_documents
        SET raw_text = NULL
        WHERE created_at < %s AND raw_text IS NOT NULL
        RETURNING id
    """, (cutoff,))
    cleared_docs = cur.rowcount
    log.info(f"  Cleared raw_text from {cleared_docs} transcript_documents")

    # ── Commit ────────────────────────────────────────────────────────────────
    neon.commit()
    cur.close()
    neon.close()

    log.info("")
    log.info("=" * 60)
    log.info(f"Purge complete:")
    log.info(f"  management_commentary rows deleted:    {deleted_mc}")
    log.info(f"  transcript_intelligence rows deleted:  {deleted_ti}")
    log.info(f"  transcript_documents raw_text cleared: {cleared_docs}")
    log.info("=" * 60)


def storage_summary():
    """Print current row counts and estimated sizes."""
    neon = get_neon()
    cur  = neon.cursor()
    log.info("")
    log.info("Current Neon storage — management commentary tables:")
    for table in ["management_commentary", "transcript_intelligence", "transcript_documents", "management_quality_history"]:
        try:
            cur.execute(f"SELECT COUNT(*), MAX(updated_at) FROM {table}")
            count, latest = cur.fetchone()
            log.info(f"  {table:40} {count:6} rows  (latest: {latest.date() if latest else 'N/A'})")
        except:
            log.info(f"  {table:40} table not found")
    cur.close()
    neon.close()


def main():
    parser = argparse.ArgumentParser(description="Purge old management commentary from Neon")
    parser.add_argument("--execute", action="store_true", help="Actually delete (default is dry run)")
    parser.add_argument("--archive", action="store_true", help="Archive to local Postgres before deleting")
    parser.add_argument("--summary", action="store_true", help="Just show storage summary")
    args = parser.parse_args()

    if not DATABASE_URL:
        log.error("DATABASE_URL not set")
        sys.exit(1)

    storage_summary()

    if args.summary:
        return

    log.info("")
    if args.execute:
        execute_purge(args.archive)
    else:
        dry_run()


if __name__ == "__main__":
    main()
