"""Offline regressions for the derived-stage psycopg2 query contract."""
import inspect

import completeness
import drive
import score_engine


class OwnerRowCursor:
    def __init__(self):
        self.query = ""

    def execute(self, query, _params=None):
        self.query = " ".join(query.split())

    def fetchone(self):
        if "FROM ipo_issue" in self.query:
            return (100, 105, 95, 500, 50)
        return None

    def fetchall(self):
        if "FROM financial_statements" in self.query:
            return [("31-Mar-25", "Consolidated", 500, 80, 40, 200, 20, 300)]
        if "FROM source_facts" in self.query:
            return []
        return []


class OwnerRowConnection:
    def cursor(self):
        return OwnerRowCursor()


def test_drive_derived_accepts_real_issue_tuple_in_dry_and_write_modes(monkeypatch):
    writes = []
    monkeypatch.setattr(score_engine, "write_valuation", lambda conn, value: writes.append(value))

    dry = drive.step_derived(OwnerRowConnection(), 5, False)
    live = drive.step_derived(OwnerRowConnection(), 12, True)

    assert dry["status"] == "dry"
    assert live["status"] == "ok"
    assert len(writes) == 1
    assert dry["score"] is not None and live["score"] == dry["score"]


def test_parameterized_consolidated_queries_escape_psycopg_percent_wildcards():
    score_source = inspect.getsource(score_engine._latest_financials)
    completeness_source = inspect.getsource(completeness.check_completeness)
    assert "ILIKE '%%consolidat%%'" in score_source
    assert "ILIKE '%%consolidat%%'" in completeness_source
    assert "ILIKE '%consolidat%'" not in score_source
    assert "ILIKE '%consolidat%'" not in completeness_source
