"""Regression coverage for canonical IPO lookup in the --year-min path."""
import datetime
import pathlib
import sys
import types

import rhp_sonnet


class _Cursor:
    def __init__(self):
        self.query = None

    def execute(self, query):
        self.query = query

    def fetchall(self):
        return [
            ("Recent Industries Limited", datetime.date(2025, 2, 3)),
            ("Old Industries Ltd", datetime.date(2019, 1, 2)),
        ]


class _Connection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.closed = False

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


def test_year_min_reads_canonical_ipo_and_filters_pdfs(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-never-used")
    scan = tmp_path / "rhps"
    recent = scan / "Recent-Industries" / "rhp.pdf"
    old = scan / "Old-Industries" / "rhp.pdf"
    recent.parent.mkdir(parents=True)
    old.parent.mkdir(parents=True)
    recent.write_bytes(b"pdf")
    old.write_bytes(b"pdf")

    cursor = _Cursor()
    connection = _Connection(cursor)
    monkeypatch.setitem(sys.modules, "fitz", types.ModuleType("fitz"))
    sections = types.ModuleType("rhp_sections")
    sections.gather_sections = lambda _path: {}
    monkeypatch.setitem(sys.modules, "rhp_sections", sections)
    database = types.ModuleType("psycopg2")
    database.connect = lambda *_args, **_kwargs: connection
    monkeypatch.setitem(sys.modules, "psycopg2", database)
    monkeypatch.setattr(
        sys,
        "argv",
        ["rhp_sonnet.py", "--dir", str(scan), "--year-min", "2021", "--cap", "0"],
    )

    rhp_sonnet.main()

    assert cursor.query == "SELECT name_display, listing_date FROM ipo WHERE listing_date IS NOT NULL"
    assert connection.closed
    assert "1 RHPs listed 2021+" in capsys.readouterr().out
