#!/usr/bin/env python3
"""
apply_prod_schema.py — applies _scripts/migrations/20260617_prod_ready_tables.sql
to DATABASE_URL, ONE STATEMENT AT A TIME so a single failure can't roll back the rest.

Why per-statement: some prod tables (e.g. ipo_intelligence) already exist on Neon with
an older schema, so `CREATE TABLE IF NOT EXISTS` skips them and a later
`CREATE INDEX ... (status)` fails on the missing column. Run as one batch, that failure
rolled back price_candles too. Per-statement + autocommit isolates each one.

Local: set DATABASE_URL to Neon, then  python _scripts/apply_prod_schema.py
"""
import os, sys, psycopg2

MIGRATION = os.path.join(os.path.dirname(__file__), "migrations", "20260617_prod_ready_tables.sql")

def statements(sql: str):
    for chunk in sql.split(";"):
        # drop comment-only lines; keep real SQL
        body = "\n".join(l for l in chunk.splitlines() if not l.strip().startswith("--"))
        if body.strip():
            yield chunk.strip() + ";"

def main():
    url = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL not set")
    sql = open(MIGRATION, "r", encoding="utf-8").read()

    conn = psycopg2.connect(url, connect_timeout=20)
    conn.autocommit = True                      # each statement commits on its own
    cur = conn.cursor()

    applied, skipped = 0, []
    for stmt in statements(sql):
        try:
            cur.execute(stmt)
            applied += 1
        except Exception as e:
            label = " ".join(stmt.split()[:6])
            skipped.append((label, str(e).strip().splitlines()[0]))

    cur.execute("SELECT to_regclass('public.price_candles')")
    have_pc = cur.fetchone()[0]
    cur.close(); conn.close()

    print(f"applied {applied} statements; skipped {len(skipped)}")
    for label, why in skipped:
        print(f"  skipped: {label} …  ({why})")
    if not have_pc:
        sys.exit("price_candles STILL missing — investigate above")
    print("price_candles present ✓  — generate_signals can now read it")

if __name__ == "__main__":
    main()
