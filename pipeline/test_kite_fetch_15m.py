import datetime as dt

from pipeline.kite_fetch_15m import insert_bars, is_transient


class Cursor:
    rowcount = 0
    def execute(self, sql, params):
        assert "ON CONFLICT (ipo_id,ts) DO NOTHING" in sql
        self.rowcount = int(params[1].minute == 15)


class Conn:
    def __init__(self): self.commits = 0
    def cursor(self): return Cursor()
    def commit(self): self.commits += 1


def test_writer_counts_insertions_separately_from_duplicates():
    conn = Conn()
    bars = [{"ts": dt.datetime(2026, 1, 1, 9, minute), "o": 1, "h": 2, "l": 1, "c": 2, "v": 3}
            for minute in (0, 15)]
    assert insert_bars(conn, 1, bars) == 1
    assert conn.commits == 1


def test_transient_classification_is_bounded_to_transport_failures():
    assert is_transient(RuntimeError("HTTP 429"))
    assert is_transient(TimeoutError("timed out"))
    assert not is_transient(RuntimeError("column does not exist"))
