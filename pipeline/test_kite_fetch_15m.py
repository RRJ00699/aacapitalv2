import datetime as dt

import pipeline.kite_fetch_15m as lane


class WriterCursor:
    rowcount = 0
    def execute(self, sql, params):
        assert "ON CONFLICT (ipo_id,ts) DO NOTHING" in sql
        self.rowcount = int(params[1].minute == 15)


class WriterConn:
    def __init__(self): self.commits = 0
    def cursor(self): return WriterCursor()
    def commit(self): self.commits += 1


def test_writer_counts_insertions_separately_from_duplicates():
    conn = WriterConn()
    bars = [{"ts": dt.datetime(2026, 1, 1, 9, minute), "o": 1, "h": 2, "l": 1, "c": 2, "v": 3}
            for minute in (0, 15)]
    assert lane.insert_bars(conn, 1, bars) == 1
    assert conn.commits == 1


def test_selector_is_progress_safe_without_issue_size_exclusion():
    class Cursor:
        def execute(self, sql, params):
            normalized = " ".join(sql.split())
            assert "issue_size_cr" not in normalized
            assert "issue_size_cr" not in normalized
            assert "c.latest ASC NULLS FIRST" in normalized
            assert "i.id = ANY(%s)" in normalized
            assert "LIMIT" not in normalized
            assert params == [[9, 3]]
        def fetchall(self): return []
    class Conn:
        def cursor(self): return Cursor()
    assert lane.select_targets(Conn(), 2, [9, 3]) == []


def test_existing_timezone_aware_max_resumes_next_bar_and_inserts_only_new(monkeypatch):
    latest = dt.datetime(2026, 1, 2, 10, 30, tzinfo=dt.timezone.utc)
    class Cursor:
        def execute(self, sql, params): pass
        def fetchone(self): return (latest,)
    class Conn:
        def cursor(self): return Cursor()
        def rollback(self): raise AssertionError("rerun must not fail")
    target = (7, "INE", "", "Small Mainboard", dt.datetime.now(lane.IST).date(), 77, True, "listed")
    monkeypatch.setattr(lane, "select_targets", lambda conn, limit, ids: [target])
    monkeypatch.setattr(lane, "get_kite", lambda: object())
    requested = []
    new_ts = latest + dt.timedelta(minutes=15)
    def fetch(_kite, token, start, end):
        requested.append((token, start, end))
        assert isinstance(start, dt.datetime) and start.tzinfo
        assert isinstance(end, dt.datetime) and end.tzinfo
        assert start == new_ts.astimezone(lane.IST)
        return [{"ts": new_ts, "o": 1, "h": 2, "l": 1, "c": 2, "v": 3}]
    monkeypatch.setattr(lane, "fetch_candles_15m", fetch)
    monkeypatch.setattr(lane, "insert_bars", lambda conn, ipo_id, bars: 1)
    result = lane.run(Conn(), limit=1, ids=[7], dry_run=False, throttle_seconds=0, sleep=lambda _: None)
    assert len(requested) == 1
    assert result["bars_received"] == result["bars_inserted"] == 1
    assert result["duplicates"] == 0


def test_transient_classification_is_bounded_to_transport_failures():
    assert lane.is_transient(RuntimeError("HTTP 429"))
    assert lane.is_transient(TimeoutError("timed out"))
    assert not lane.is_transient(RuntimeError("column does not exist"))


def test_explicit_ids_are_deduplicated_and_every_unique_id_has_one_outcome(monkeypatch):
    today = dt.datetime.now(lane.IST).date()
    rows = [(1,"I","", "eligible small",today,11,True,"listed"),
            (2,"I","", "announced no issue",None,None,True,"announced"),
            (3,"I","", "SME",today,33,False,"listed")]
    monkeypatch.setattr(lane, "select_targets", lambda *_: rows)
    result = lane.run(object(), limit=1, ids=lane.parse_ids("1,2,3,4,1"), dry_run=True)
    assert result["requested"] == 4 and result["eligible"] == 1
    assert result["exclusions"] == {"missing_listing_date":1,
                                     "out_of_universe":1, "not_found":1}
    assert len(result["ipos"]) == 4
