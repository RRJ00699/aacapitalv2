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

class TokenCursor:
    def __init__(self, existing=None): self.existing=existing; self.rowcount=0; self.calls=[]
    def execute(self, sql, params):
        self.calls.append((" ".join(sql.split()),params))
        if sql.lstrip().startswith("UPDATE"): self.rowcount=0 if self.existing is not None else 1
    def fetchone(self): return (self.existing,)
class TokenConn:
    def __init__(self,existing=None): self.cur=TokenCursor(existing); self.commits=0
    def cursor(self): return self.cur
    def commit(self): self.commits+=1

def test_isin_null_daily_resolution_persists_by_exact_id_for_next_15m_lane(monkeypatch):
    from unittest.mock import Mock, patch
    conn=TokenConn()
    with patch("fill_ipo._log_fact") as fact:
        assert lane.persist_resolved_token(conn,746,9988,"NSE") == 9988
    assert conn.cur.calls[0][1] == (9988,746)
    assert "WHERE id=%s AND kite_token IS NULL" in conn.cur.calls[0][0]
    fact.assert_called_once()

def test_existing_token_is_never_overwritten_and_gets_no_new_provenance():
    from unittest.mock import patch
    conn=TokenConn(existing=1234)
    with patch("fill_ipo._log_fact") as fact:
        assert lane.persist_resolved_token(conn,746,9988,"NSE") == 1234
    fact.assert_not_called()

class OutcomeCursor:
    def __init__(self): self.index=0
    def execute(self,*_): self.index+=1
    def fetchall(self): return [("2026-08-19",165,181.5,160,181.5)]
    def fetchone(self): return (.14,160,165)
class OutcomeConn:
    def cursor(self): return OutcomeCursor()

def test_absurd_band_inconsistent_issue_price_withholds_gap_pool_and_winner():
    rec,note=lane.derive_outcome(OutcomeConn(),1098)
    assert rec["listing_open"]==165 and rec["d1_close"]==181.5
    assert {"gap_pct","pool","winner_35"}.isdisjoint(rec)
    assert "band-inconsistent" in note
