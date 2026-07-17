#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_write_constraints.py — GUARDRAIL A: every table a writer INSERTs into
must own a UNIQUE index (natural key), else cleanups without constraints let
duplicates return (the recurring double-Laser). Fails CI/lean if a written
table has no unique index. Advisory list is explicit and reviewed.
"""
import os, sys
import psycopg2

# tables writers insert into that MUST have a dedupe key
REQUIRE_UNIQUE = [
    "ipo_intelligence", "ipo_consolidated", "ipo_verdicts", "ipo_rhp_intel",
    "ipo_research_notes", "ipo_preopen_book", "ipo_tick_feed", "ipo_level_analysis",
]

def main():
    conn = psycopg2.connect(os.environ["DATABASE_URL"]); cur = conn.cursor()
    missing = []
    for t in REQUIRE_UNIQUE:
        cur.execute("""SELECT COUNT(*) FROM pg_indexes
            WHERE tablename = %s AND indexdef ILIKE '%%UNIQUE%%'""", (t,))
        if cur.fetchone()[0] == 0:
            missing.append(t)
    conn.close()
    if missing:
        print("GUARDRAIL A FAIL — writer tables without a UNIQUE index:")
        for t in missing: print("  " + t)
        print("Add a natural-key UNIQUE index in schema_sync.py before writing to these.")
        sys.exit(1)
    print(f"GUARDRAIL A: all {len(REQUIRE_UNIQUE)} writer tables have a UNIQUE index")

if __name__ == "__main__":
    main()
