#!/usr/bin/env python3
"""Tables that may PRE-EXIST must be repaired with ALTERs, not just CREATE.

`CREATE TABLE IF NOT EXISTS` is a NO-OP when the table already exists — it will
NOT add missing columns. This bit us twice:

  2026-07-18  trade_journal      lacked action/broker/broker_order_id/... ->
                                 "SCHEMA MISMATCH. Refusing to guess."
  2026-07-19  ipo_preopen_book   lacked `source` entirely -> UndefinedColumn

Both had a CREATE in schema_sync that silently did nothing. Any table whose
CREATE lists columns the code depends on must ALSO have per-column ALTERs.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SYNC = ROOT / "_scripts" / "schema_sync.py"
pytestmark = pytest.mark.unit

# tables known to exist in production before schema_sync managed them
PRE_EXISTING = ["trade_journal", "ipo_preopen_book", "ipo_research_notes"]


def _ddl():
    return SYNC.read_text(encoding="utf-8")


@pytest.mark.parametrize("table", PRE_EXISTING)
def test_pre_existing_table_has_alters(table):
    s = _ddl()
    alters = re.findall(rf"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS (\w+)", s)
    assert alters, (
        f"{table} relies only on CREATE TABLE IF NOT EXISTS — a no-op on an "
        f"existing table. Missing columns will never be added.")


def test_preopen_book_has_source_column():
    """The exact 2026-07-19 failure: `column \"source\" does not exist`."""
    assert "ALTER TABLE ipo_preopen_book ADD COLUMN IF NOT EXISTS source" in _ddl()


def test_trade_journal_has_broker_order_id():
    """The exact 2026-07-18 failure."""
    assert "ALTER TABLE trade_journal ADD COLUMN IF NOT EXISTS broker_order_id" in _ddl()
