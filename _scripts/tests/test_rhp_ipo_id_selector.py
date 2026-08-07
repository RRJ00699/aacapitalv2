"""The owner activation selector must make an RHP run provably one-IPO bounded."""
import importlib.util
import io
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "_scripts" / "fetch_new_rhps.py"


def load_module():
    spec = importlib.util.spec_from_file_location("fetch_new_rhps_single", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.sql = None
        self.params = None

    def execute(self, sql, params):
        self.sql, self.params = sql, params

    def fetchall(self):
        return self.rows


class Connection:
    def __init__(self, rows):
        self.cursor_instance = Cursor(rows)

    def cursor(self):
        return self.cursor_instance

    def close(self):
        pass


def run_query(monkeypatch, rows, ipo_id=None):
    connection = Connection(rows)
    monkeypatch.setenv("DATABASE_URL", "postgresql://unit.invalid/db")
    monkeypatch.setitem(sys.modules, "psycopg2", SimpleNamespace(connect=lambda *_a, **_k: connection))
    result = load_module().new_ipos_without_rhp(45, ipo_id=ipo_id)
    return result, connection.cursor_instance


def test_exact_one_selector_uses_neon_id_and_returns_one(monkeypatch):
    owner = (304, "Owner Selected Limited", "INE000000304", "2026-08-06")
    rows, cursor = run_query(monkeypatch, [owner], ipo_id=304)
    assert rows == [owner]
    assert "AND i.id = %s" in cursor.sql
    assert cursor.params == (45, 45, 45, 304)


@pytest.mark.parametrize("reason", ["nonexistent", "ineligible", "already-stored"])
def test_missing_or_ineligible_exact_id_fails_nonzero(monkeypatch, reason):
    with pytest.raises(SystemExit, match="missing, ineligible") as error:
        run_query(monkeypatch, [], ipo_id=999)
    assert error.value.code != 0, reason


def test_second_target_can_never_execute(monkeypatch):
    rows = [
        (304, "First Limited", "INE000000304", "2026-08-06"),
        (305, "Second Limited", "INE000000305", "2026-08-06"),
    ]
    with pytest.raises(SystemExit, match="refusing an unbounded run") as error:
        run_query(monkeypatch, rows, ipo_id=304)
    assert error.value.code != 0


def test_scheduled_query_without_selector_is_unchanged_and_unbounded(monkeypatch):
    owners = [
        (304, "First Limited", "INE000000304", "2026-08-06"),
        (305, "Second Limited", "INE000000305", "2026-08-06"),
    ]
    rows, cursor = run_query(monkeypatch, owners)
    assert rows == owners
    assert "AND i.id = %s" not in cursor.sql
    assert cursor.params == (45, 45, 45)


@pytest.mark.parametrize("value", ["0", "-1", "abc"])
def test_selector_requires_positive_integer(value):
    with pytest.raises(Exception, match="positive integer"):
        load_module()._positive_ipo_id(value)


def test_windows_import_never_replaces_or_closes_stdout(monkeypatch):
    stream = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stream)
    monkeypatch.setattr(sys, "platform", "win32")
    load_module()
    assert sys.stdout is stream
    assert not stream.closed
    stream.write("capture remains writable")


def test_exact_selector_compiles_against_live_readonly_schema():
    url = os.environ.get("NEON_READONLY_DATABASE_URL")
    if not url:
        pytest.skip("NEON_READONLY_DATABASE_URL not available")
    import psycopg2

    module = load_module()
    sql, params = module.selector_query(45, ipo_id=1)
    conn = psycopg2.connect(url, connect_timeout=20)
    try:
        conn.set_session(readonly=True, autocommit=False)
        cur = conn.cursor()
        cur.execute("EXPLAIN " + sql, params)
        assert cur.fetchall()
        conn.rollback()
    finally:
        conn.close()
