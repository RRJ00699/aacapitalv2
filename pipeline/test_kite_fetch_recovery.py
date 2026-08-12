"""Regression coverage for owner A2's stale daily-Kite DB connection failure."""
import sys

import pipeline.kite_fetch as kite_fetch


class Connection:
    def __init__(self, rows=None, *, fail=False):
        self.rows = rows or []
        self.fail = fail
        self.closed = False

    def cursor(self):
        if self.fail:
            raise kite_fetch.psycopg2.InterfaceError("connection already closed")
        return self

    def execute(self, _sql, _params=None):
        if self.fail:
            raise kite_fetch.psycopg2.InterfaceError("connection already closed")

    def fetchall(self):
        return self.rows

    def close(self):
        self.closed = True


def test_closed_connection_before_first_ipo_does_not_cascade(monkeypatch, capsys):
    targets = [(n, f"ISIN{n}", f"SYM{n}", f"IPO {n}", None) for n in range(1, 11)]
    selector = Connection(targets)
    per_ipo = [Connection(fail=True)] + [Connection() for _ in range(9)]
    connections = iter([selector, *per_ipo])
    monkeypatch.setattr(kite_fetch, "connect_db", lambda: next(connections))

    kite = object()
    def authenticate():
        assert selector.closed, "selection connection must close before Kite network/auth"
        return kite
    monkeypatch.setattr(kite_fetch, "get_kite", authenticate)
    monkeypatch.setattr(kite_fetch, "instruments", lambda _kite: [{}])

    completed = []
    def process(connect, _kite, ipo_id, *_args):
        conn = connect()
        try:
            conn.cursor()  # first IPO observes the stale/closed connection
        finally:
            conn.close()
        completed.append(ipo_id)
        return {"token": ipo_id, "bars": 0, "bars_15m": 0,
                "outcome": None, "notes": []}
    monkeypatch.setattr(kite_fetch, "process", process)
    monkeypatch.setattr(sys, "argv", ["kite_fetch.py", "--limit", "10", "--write", "--no-15m"])

    assert kite_fetch.main() is None
    output = capsys.readouterr()
    assert completed == list(range(2, 11))
    assert "9/10 with a token · 1 failed" in output.out
    assert "Traceback (most recent call last)" in output.err

