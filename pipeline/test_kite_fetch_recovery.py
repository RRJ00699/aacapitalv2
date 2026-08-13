import sys

import pytest

import pipeline.kite_fetch as lane


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, *_args, **_kwargs):
        return None

    def fetchall(self):
        return self.rows


class Connection:
    def __init__(self, rows=()):
        self.closed = False
        self.rows = rows

    def cursor(self):
        assert not self.closed
        return Cursor(self.rows)

    def close(self):
        self.closed = True


def test_target_connection_is_closed_before_kite_authentication(monkeypatch):
    target_conn = Connection([])
    monkeypatch.setattr(lane, "db", lambda: target_conn)
    monkeypatch.setattr(sys, "argv", ["kite_fetch.py", "--write", "--no-15m"])

    def authenticate():
        assert target_conn.closed
        return object()

    monkeypatch.setattr(lane, "get_kite", authenticate)
    monkeypatch.setattr(lane, "instruments", lambda _kite: [])
    lane.main()


def test_with_db_always_closes_a_failed_connection(monkeypatch):
    connection = Connection()
    monkeypatch.setattr(lane, "db", lambda: connection)

    with pytest.raises(RuntimeError, match="database failed"):
        lane.with_db(lambda _conn: (_ for _ in ()).throw(RuntimeError("database failed")))

    assert connection.closed


def test_later_ipo_runs_after_earlier_ipo_database_failure(monkeypatch, capsys):
    targets = [(1, "isin-1", "ONE", "One", None),
               (2, "isin-2", "TWO", "Two", None)]
    target_conn = Connection(targets)
    monkeypatch.setattr(lane, "db", lambda: target_conn)
    monkeypatch.setattr(sys, "argv", ["kite_fetch.py", "--write", "--no-15m"])
    monkeypatch.setattr(lane, "get_kite", lambda: object())
    monkeypatch.setattr(lane, "instruments", lambda _kite: [])
    called = []

    def process(_kite, ipo_id, *_args, **_kwargs):
        called.append(ipo_id)
        if ipo_id == 1:
            raise RuntimeError("connection already closed")
        return {"token": 22, "resolved_by": "already stored", "bars": 1,
                "bars_15m": 0, "outcome": None, "notes": []}

    monkeypatch.setattr(lane, "process", process)
    with pytest.raises(SystemExit) as exc:
        lane.main()
    assert exc.value.code == 1
    output = capsys.readouterr().out
    assert called == [1, 2]
    assert "Traceback (most recent call last)" in output
    assert "connection already closed" in output


def test_no_database_connection_spans_kite_network_call(monkeypatch):
    connections = []

    def new_connection():
        connection = Connection()
        connections.append(connection)
        return connection

    monkeypatch.setattr(lane, "db", new_connection)
    lane.with_db(lambda conn: conn.cursor().execute("SELECT 1"))
    assert all(connection.closed for connection in connections)
    # This stands in for authentication/instrument/candle HTTP work.
    assert all(connection.closed for connection in connections)


def test_dry_run_is_kite_network_free_and_write_free(monkeypatch):
    target_conn = Connection([(7, "isin", "SEVEN", "Seven", None)])
    monkeypatch.setattr(lane, "db", lambda: target_conn)
    monkeypatch.setattr(sys, "argv", ["kite_fetch.py", "--dry-run"])
    monkeypatch.setattr(lane, "get_kite",
                        lambda: pytest.fail("dry-run authenticated with Kite"))
    lane.main()
    assert target_conn.closed
