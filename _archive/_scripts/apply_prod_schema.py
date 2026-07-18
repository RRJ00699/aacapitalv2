#!/usr/bin/env python3
"""
apply_prod_schema.py — applies _scripts/migrations/20260617_prod_ready_tables.sql
ONE STATEMENT AT A TIME (a single failure can't roll back the rest), then ensures a
few tables the migration forgot. Self-healing: safe to run every pipeline run.

Fixes:
  - relation "price_candles" does not exist        (migration never applied to Neon)
  - relation "price_candles_weekly" does not exist (table not in the migration at all)
"""
import os, sys, psycopg2

MIGRATION = os.path.join(os.path.dirname(__file__), "migrations", "20260617_prod_ready_tables.sql")

# Tables written by the pipeline but missing from the migration file.
EXTRA_TABLES = [
    """CREATE TABLE IF NOT EXISTS price_candles_weekly (
        symbol     TEXT,
        week_start DATE,
        open       NUMERIC,
        high       NUMERIC,
        low        NUMERIC,
        close      NUMERIC,
        volume     BIGINT,
        PRIMARY KEY (symbol, week_start)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_pcw_symbol ON price_candles_weekly (symbol)",
]

def statements(sql: str):
    for chunk in sql.split(";"):
        body = "\n".join(l for l in chunk.splitlines() if not l.strip().startswith("--"))
        if body.strip():
            yield chunk.strip() + ";"

def main():
    url = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL not set")
    sql = open(MIGRATION, "r", encoding="utf-8").read()

    conn = psycopg2.connect(url, connect_timeout=20)
    conn.autocommit = True
    cur = conn.cursor()

    applied, skipped = 0, []
    for stmt in list(statements(sql)) + EXTRA_TABLES:
        try:
            cur.execute(stmt)
            applied += 1
        except Exception as e:
            skipped.append((" ".join(stmt.split()[:6]), str(e).strip().splitlines()[0]))

    have = {}
    for t in ("price_candles", "price_candles_weekly", "technical_signals"):
        cur.execute("SELECT to_regclass(%s)", (f"public.{t}",))
        have[t] = cur.fetchone()[0] is not None
    cur.close(); conn.close()

    print(f"applied {applied} statements; skipped {len(skipped)}")
    for label, why in skipped:
        print(f"  skipped: {label} …  ({why})")
    print("tables present:", ", ".join(f"{k}={'✓' if v else '✗'}" for k, v in have.items()))
    missing = [k for k, v in have.items() if not v]
    if missing:
        sys.exit(f"STILL missing: {missing}")
    print("schema OK — candle + signal tables all present")

if __name__ == "__main__":
    main()
