#!/usr/bin/env python3
"""ipo_gold view generator EXECUTED against real Postgres, including the exact
prod failure: ipo_consolidated already carrying an overlapping column (isin)."""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))


def test_generator_handles_overlap_and_serves_one_object(pg_uri):
    import psycopg2
    from schema_sync import build_ipo_gold_view, GOLD_COLS
    conn = psycopg2.connect(pg_uri); conn.autocommit = True; cur = conn.cursor()
    for stmt in ("DROP VIEW IF EXISTS ipo_gold", "DROP TABLE IF EXISTS ipo_gold"):
        try: cur.execute(stmt)
        except Exception: pass  # whichever form the previous test left
    cur.execute("DROP TABLE IF EXISTS ipo_consolidated, ipo_golden CASCADE")
    # prod shape: consolidated ALREADY has isin (the 84/85 failure) + own cols
    cur.execute("""CREATE TABLE ipo_consolidated (
        company_name TEXT, symbol TEXT, issue_price NUMERIC, isin TEXT)""")
    cur.execute("""CREATE TABLE ipo_golden (
        company_key TEXT PRIMARY KEY, company_name TEXT, nse_symbol TEXT,
        isin TEXT, lot_size INT, candles_json JSONB, golden_filled_at TIMESTAMPTZ)""")
    cur.execute("""INSERT INTO ipo_consolidated VALUES
        ('SBI Funds Management Ltd.', 'SBIFUNDS', 574, NULL)""")
    cur.execute("""INSERT INTO ipo_golden (company_key, company_name, isin, lot_size, candles_json)
        VALUES ('sbifundsmanagement', 'SBI Funds Management Ltd.', 'INE640G01020', 26,
                '[{"d":"2026-07-21","o":613.3,"c":609.75}]')""")
    ddl = build_ipo_gold_view(cur)
    cur.execute(ddl)  # the prod statement — must not raise 'specified more than once'
    cur.execute("""SELECT isin, lot_size, issue_price,
                          json_array_length(candles_json::json)
                   FROM ipo_gold WHERE company_name ILIKE '%SBI Funds%'""")
    isin, lot, price, days = cur.fetchone()
    assert isin == "INE640G01020", "overlap column COALESCEs golden when consolidated is NULL"
    assert lot == 26 and float(price) == 574 and days == 1
    # golden-only columns present even though consolidated lacks them
    cur.execute("SELECT golden_filled_at FROM ipo_gold LIMIT 1")
    # regen after a consolidated rebuild that DROPS isin — view must adapt
    cur.execute("DROP VIEW ipo_gold")
    cur.execute("ALTER TABLE ipo_consolidated DROP COLUMN isin")
    cur.execute(build_ipo_gold_view(cur))
    cur.execute("SELECT isin FROM ipo_gold WHERE company_name ILIKE '%SBI%'")
    assert cur.fetchone()[0] == "INE640G01020", "after rebuild drops the column, golden still serves it"
    assert all(c in ddl for c in ("COALESCE", "LEFT JOIN ipo_golden")) and GOLD_COLS
    conn.close()
