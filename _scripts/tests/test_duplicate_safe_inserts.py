#!/usr/bin/env python3
"""Every INSERT into a STATE table must be duplicate-safe.

Owner rule 2026-07-18: "each insert is duplicate safe. Data should be gold standard."

Two kinds of table:
  * STATE tables (one row per entity) — re-running the pipeline must NOT create a
    second row, so the INSERT needs ON CONFLICT (or a proven pre-check + unique index).
  * EVENT/LOG tables (one row per occurrence) — duplicates are CORRECT. Every
    pipeline failure and every AI-spend attempt is its own event.

2026-07-18: sync_trade_journal INSERTed into trade_journal whose broker_order_id
is UNIQUE (added by schema_sync) — re-syncing the same Zerodha order RAISED
instead of no-op'ing. Fixed with ON CONFLICT DO NOTHING.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "_scripts"
pytestmark = pytest.mark.unit

# table -> must the INSERT be conflict-guarded?
EVENT_TABLES = {"pipeline_failures", "pipeline_steps", "rhp_run_log",
                "sbi_haiku_run_log", "job_runs", "nse_preopen_raw", "ipo_tick_feed"}
STATE_INSERTS = {
    "_scripts/sync_trade_journal.py": "trade_journal",
}


@pytest.mark.parametrize("relpath,table", STATE_INSERTS.items())
def test_state_insert_is_conflict_guarded(relpath, table):
    src = (ROOT / relpath).read_text(encoding="utf-8")
    assert f"INSERT INTO {table}" in src, f"{relpath} no longer inserts into {table}"
    assert "ON CONFLICT" in src, (
        f"{relpath}: INSERT INTO {table} has no ON CONFLICT — re-running the sync "
        f"will raise or duplicate"
    )


def test_event_tables_are_not_over_guarded():
    """An event log with ON CONFLICT DO NOTHING would silently DROP real events."""
    for name in ("check_freshness.py", "check_date_sanity.py"):
        p = SCRIPTS / name
        if not p.exists():
            continue
        src = p.read_text(encoding="utf-8")
        if "INSERT INTO pipeline_failures" in src:
            seg = src[src.index("INSERT INTO pipeline_failures"):][:400]
            assert "ON CONFLICT" not in seg, \
                f"{name}: pipeline_failures is an EVENT log — dedupe would drop failures"


def test_no_unguarded_insert_into_core_ipo_tables():
    """ipo_intelligence / ipo_consolidated are STATE. Any INSERT must be guarded
    by ON CONFLICT or a documented pre-existence check."""
    offenders = []
    for p in SCRIPTS.rglob("*.py"):
        if "_archive" in p.parts or "tests" in p.parts:
            continue
        src = p.read_text(encoding="utf-8", errors="ignore")
        for tbl in ("ipo_intelligence", "ipo_consolidated"):
            if f"INSERT INTO {tbl}" not in src:
                continue
            seg = src[src.index(f"INSERT INTO {tbl}"):][:600]
            guarded = "ON CONFLICT" in seg or "fetchone()" in src or "existing" in src
            if not guarded:
                offenders.append(f"{p.relative_to(ROOT)} -> {tbl}")
    assert not offenders, f"unguarded INSERT into core state table(s): {offenders}"
