#!/usr/bin/env python3
"""
migrate_neon_to_local.py  —  move heavy OFFLINE-only tables from Neon to local Postgres.

Run this ON YOUR MACHINE (where both Neon and localhost:5432 are reachable).
It will NOT run from GitHub Actions — GitHub's cloud cannot reach your local DB.

What it does, per table:  copy Neon -> local (pg_dump | psql)  ->  verify row counts
                          ->  (only with --drop) DROP it from Neon to reclaim space.

Default is DRY-RUN: it prints the plan and the sizes, touches nothing.

Usage (PowerShell):
  $env:DATABASE_URL="postgresql://...neon..."          # source
  $env:LOCAL_DATABASE_URL="postgresql://postgres:pw@localhost:5432/aacapital"
  python migrate_neon_to_local.py                       # dry-run, shows plan
  python migrate_neon_to_local.py --copy                # copy + verify, keep on Neon
  python migrate_neon_to_local.py --copy --drop         # copy + verify + free Neon

Requires: pg_dump / psql on PATH (you have PostgreSQL 18 locally), psycopg2-binary.
"""
import argparse, os, subprocess, sys
import psycopg2

# Offline-only, heavy, NOT served by the live UI -> safe to move to local.
# (The app reads computed thin tables + price_monthly + ipo_intelligence, which STAY on Neon.)
DEFAULT_OFFLOAD = [
    "price_weekly",          # ~69 MB, used only to compute weekly_dna offline
    "price_candles",         # raw daily OHLC, used only to compute signals offline
    "price_candles_weekly",
    "institutional_deals",   # ~27 MB raw deals, used only to compute smart_money_summary
]
# Explicitly KEEP on Neon (listed so you don't move them by accident):
KEEP_ON_NEON = [
    "price_monthly",         # served live by /api/price-history (charts)
    "multibagger_events",    # read by /api/dna-lab  (mirage engine — drop separately if you retire it)
    "stock_fundamentals", "weekly_dna", "earnings_events", "earnings_signals",
    "smart_money_summary", "sector_rotation", "order_book_summary", "order_book_signals",
    "management_commentary", "market_snapshot", "ipo_intelligence", "ipo_live",
]

def count(dsn, table):
    try:
        with psycopg2.connect(dsn) as c, c.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM {table}")
            return cur.fetchone()[0]
    except Exception as e:
        return f"(missing: {e.__class__.__name__})"

def size(dsn, table):
    try:
        with psycopg2.connect(dsn) as c, c.cursor() as cur:
            cur.execute("SELECT pg_size_pretty(pg_total_relation_size(%s))", (table,))
            return cur.fetchone()[0]
    except Exception:
        return "?"

def copy_table(src, dst, table):
    # pg_dump a single table (schema+data) from Neon, pipe straight into local psql.
    dump = subprocess.Popen(
        ["pg_dump", "--no-owner", "--no-privileges", "--clean", "--if-exists",
         "-t", table, src], stdout=subprocess.PIPE)
    load = subprocess.Popen(["psql", dst], stdin=dump.stdout)
    dump.stdout.close()
    load.communicate()
    return load.returncode == 0 and dump.wait() == 0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tables", nargs="*", default=DEFAULT_OFFLOAD)
    ap.add_argument("--copy", action="store_true", help="actually copy Neon->local")
    ap.add_argument("--drop", action="store_true", help="after verified copy, DROP from Neon")
    a = ap.parse_args()

    src = os.environ.get("DATABASE_URL")
    dst = os.environ.get("LOCAL_DATABASE_URL")
    if not src or not dst:
        sys.exit("Set DATABASE_URL (Neon) and LOCAL_DATABASE_URL (localhost) first.")

    print(f"{'TABLE':24} {'NEON rows':>12} {'NEON size':>10}  -> action")
    print("-" * 64)
    for t in a.tables:
        nrows = count(src, t)
        print(f"{t:24} {str(nrows):>12} {size(src,t):>10}  -> "
              f"{'COPY' + ('+DROP' if a.drop else '') if a.copy else 'dry-run'}")
        if not a.copy:
            continue
        if not str(nrows).isdigit():
            print(f"   skip {t}: not present on Neon"); continue
        if not copy_table(src, dst, t):
            print(f"   ERROR copying {t} — stopping, nothing dropped."); sys.exit(1)
        lrows = count(dst, t)
        if str(lrows) != str(nrows):
            print(f"   VERIFY FAILED {t}: neon={nrows} local={lrows} — NOT dropping."); continue
        print(f"   verified {t}: {lrows} rows on local ✓")
        if a.drop:
            with psycopg2.connect(src) as c, c.cursor() as cur:
                cur.execute(f"DROP TABLE {t}")
                c.commit()
            print(f"   dropped {t} from Neon — space reclaimed.")
    print("\nKEEP on Neon (served by live UI, not touched):")
    print("  " + ", ".join(KEEP_ON_NEON))
    if not a.copy:
        print("\nDry-run only. Re-run with --copy (then --copy --drop) when the plan looks right.")

if __name__ == "__main__":
    main()
