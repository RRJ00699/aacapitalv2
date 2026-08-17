import datetime as dt
import itertools
from pathlib import Path
import sqlite3
from unittest.mock import Mock, patch

import pytest

from nse_fetch import parse_discovery_item
from nse_identity_backfill import (parse_equity_master, quote_record, refresh,
    select_isin_candidates, select_listing_date_candidates, main as backfill_main,
    count_legacy_unresolved, _fill_empty, DB_CONNECT_TIMEOUT)
from nse_lifecycle import reconcile_discovery


class Cursor:
    def __init__(self, rows=()): self.rows, self.executed, self.rowcount = iter(rows), [], 0
    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        self.executed.append((normalized, params)); self.params = params
        self.is_count = normalized.startswith("SELECT count(*)")
    def fetchone(self): return (0,) if getattr(self, "is_count", False) else next(self.rows, None)
    def fetchall(self): return list(itertools.islice(self.rows, self.params[-1]))


class Conn:
    def __init__(self, rows=()): self.cur, self.commits, self.rollbacks, self.closes = Cursor(rows), 0, 0, 0
    def cursor(self): return self.cur
    def commit(self): self.commits += 1
    def rollback(self): self.rollbacks += 1
    def close(self): self.closes += 1


class RoutedCursor:
    def __init__(self, isin_rows, listing_rows, owners=(), legacy_count=0):
        self.isin_rows, self.listing_rows, self.owners = isin_rows, listing_rows, iter(owners)
        self.legacy_count = legacy_count
        self.executed, self.current, self.rowcount = [], [], 0
    def execute(self, sql, params=()):
        sql = " ".join(sql.split()); self.executed.append((sql, params))
        if sql.startswith("SELECT count(*)"): self.current = [(self.legacy_count,)]
        elif "isin IS NULL AND symbol" in sql: self.current = self.isin_rows[:params[-1]]
        elif "listing_date IS NULL" in sql: self.current = self.listing_rows[:params[-1]]
        elif "WHERE isin=%s" in sql: self.current = [next(self.owners, None)]
        else: self.current = []
    def fetchall(self): return self.current
    def fetchone(self): return self.current[0] if self.current and self.current[0] else None


class RoutedConn(Conn):
    def __init__(self, isin_rows, listing_rows, owners=(), legacy_count=0):
        self.cur = RoutedCursor(isin_rows, listing_rows, owners, legacy_count)
        self.commits = self.rollbacks = self.closes = 0


def discovery(name="New Limited", symbol="COLLIDE", isin=None, category="MAINBOARD"):
    return parse_discovery_item({"companyName": name, "symbol": symbol, "isin": isin,
        "category": category, "issueStartDate": "10-Aug-2026", "issueEndDate": "12-Aug-2026",
        "priceBand": "100-110", "lotSize": "10"})


@pytest.mark.parametrize(("field", "marker"), [
    ("category", "SME"), ("board", "EMERGE"),
    ("issueType", "REIT"), ("series", "INVIT"),
])
def test_discovery_structured_non_mainboard_markers_are_excluded(field, marker):
    item = {"companyName": "Structured Vehicle", "symbol": "STRUCT", "category": "IPO",
            field: f"  {marker.lower()}  "}
    assert parse_discovery_item(item) is None


def test_discovery_ordinary_ipo_control_remains_mainboard():
    row = parse_discovery_item({"companyName": "Ordinary Limited", "symbol": "ORDINARY",
                                "category": "IPO", "issueType": "BOOK BUILT",
                                "series": "EQ", "board": "MAINBOARD"})
    assert row is not None and row["is_mainboard"] is True


def test_symbol_is_never_used_as_identity_but_exact_name_is():
    conn = Conn([None])
    report, _, _, _ = reconcile_discovery(conn, [discovery()], write=False)
    assert report[0]["resolution"] == "bootstrap_required"
    assert not any("UPPER(symbol)" in sql for sql, _ in conn.cur.executed)
    exact = Conn([(9, "New Limited", "new limited", "OTHER", None, None),
                  (None, None, None, None, None, None, False, False)])
    assert reconcile_discovery(exact, [discovery()], write=False)[0][0]["ipo_id"] == 9


def test_exact_isin_still_wins():
    row = discovery(isin="INE000000001")
    conn = Conn([(7, "Owner", "owner", "OLD", None, "INE000000001"), None,
                 (None, None, None, None, None, None, False, False)])
    assert reconcile_discovery(conn, [row], write=False)[0][0]["ipo_id"] == 7
    assert sum("FROM ipo WHERE" in sql for sql, _ in conn.cur.executed) == 2


def test_isinless_announced_creation_issue_routing_and_idempotent_rerun():
    row = discovery()
    first = Conn([None])
    with patch("fill_ipo.upsert_ipo", return_value=(12, "inserted")) as spine, \
         patch("fill_v2.upsert_ipo_issue") as issue:
        report = reconcile_discovery(first, [row], write=True)[0]
    record = spine.call_args.args[1]
    assert report[0]["resolution"] == "inserted" and record["isin"] is None
    assert record["status"] == "announced" and record["is_mainboard"] is True
    assert not set(("open_date", "close_date", "band_lo", "band_hi", "lot_size")) & record.keys()
    assert issue.call_args.args[2]["lot_size"] == 10
    rerun = Conn([(12, "New Limited", "new limited", "COLLIDE", None, None),
                  (dt.date(2026,8,10),dt.date(2026,8,12),100,110,10,None,False,False)])
    with patch("fill_ipo.upsert_ipo") as spine, patch("fill_v2.upsert_ipo_issue") as issue:
        reconcile_discovery(rerun, [row], write=True)
    spine.assert_not_called(); issue.assert_not_called()


def test_new_row_bound_is_independent_and_overflow_reported():
    conn = Conn([None, None, None])
    rows = [discovery("One Ltd", "ONE"), discovery("Two Ltd", "TWO"), discovery("Three Ltd", "THREE")]
    with patch("fill_ipo.upsert_ipo", return_value=(12, "inserted")) as spine, \
         patch("fill_v2.upsert_ipo_issue"):
        report = reconcile_discovery(conn, rows, write=True, max_new_rows=1)[0]
    assert len(report) == 3
    assert [r["resolution"] for r in report] == ["inserted", "bounded_not_created", "bounded_not_created"]
    spine.assert_called_once()


def test_inserted_row_consumes_budget_when_issue_writer_fails():
    conn = Conn([None, None])
    rows = [discovery("One Ltd", "ONE"), discovery("Two Ltd", "TWO")]
    with patch("fill_ipo.upsert_ipo", return_value=(12, "inserted")) as spine, \
         patch("fill_v2.upsert_ipo_issue", side_effect=RuntimeError("issue failed")):
        report = reconcile_discovery(conn, rows, write=True, max_new_rows=1)[0]
    assert [r["resolution"] for r in report] == ["failed", "bounded_not_created"]
    assert report[0]["ipo_id"] == 12 and conn.rollbacks == 1
    spine.assert_called_once()


def test_selectors_are_bounded_and_encode_all_predicates():
    c = Conn([]); select_isin_candidates(c, dt.date(2026,8,11), 4)
    sql, params = c.cur.executed[0]
    assert "isin IS NULL" in sql and "symbol IS NOT NULL" in sql and "listing_date IS NOT NULL" in sql
    assert "BETWEEN %s AND %s" in sql
    assert "i.is_mainboard=TRUE" in sql
    assert params == (dt.date(2026,5,3), dt.date(2026,8,12), 4)
    c = Conn([]); select_listing_date_candidates(c, 3); sql, params = c.cur.executed[0]
    assert "listing_date IS NULL" in sql and "symbol IS NOT NULL" in sql
    assert "'ANNOUNCED','UPCOMING','OPEN','CLOSED'" in sql
    assert "i.is_mainboard=TRUE" in sql
    assert params == (3,)


def test_active_backfill_window_and_legacy_count_are_structured_and_bounded():
    today = dt.date(2026, 8, 17)
    c = Conn([]); select_isin_candidates(c, today, 5)
    sql, params = c.cur.executed[0]
    assert "'ANNOUNCED','UPCOMING','OPEN','CLOSED'" in sql
    assert "i.listing_date BETWEEN %s AND %s" in sql
    assert params == (dt.date(2026, 5, 9), dt.date(2026, 8, 18), 5)
    c = Conn([]); assert count_legacy_unresolved(c, today) == 0
    legacy_sql = c.cur.executed[0][0]
    assert "SELECT count(*)" in legacy_sql and "AND NOT" in legacy_sql
    assert "i.is_mainboard=TRUE" in legacy_sql


def test_historical_unresolved_rows_are_counted_without_quote_calls():
    conn = RoutedConn([], [], legacy_count=7)
    session = Mock(); session.get.return_value = Response(b"SYMBOL,NAME OF COMPANY\n")
    result = refresh(conn, session, limit=10, quote_limit=10, write=False,
                     today=dt.date(2026, 8, 17))
    assert result["selected"] == 0
    assert result["legacy_unresolved_not_retried"] == 7
    assert result["quote_calls"] == 0 and session.get.call_count == 1


def test_daily_15m_top_and_active_consumers_share_canonical_predicate():
    root = Path(__file__).parent
    consumers = ("kite_fetch.py", "kite_fetch_15m.py", "topout_online.py", "cron.py")
    for name in consumers:
        text = (root / name).read_text(encoding="utf-8")
        assert "CANONICAL_UNIVERSE_SQL" in text, name
    canonical = (root / "nse_fetch.py").read_text(encoding="utf-8")
    assert "i.is_mainboard=TRUE" in canonical


def test_selectors_execute_against_canonical_schema_fixture():
    raw = sqlite3.connect(":memory:")
    raw.executescript("""CREATE TABLE ipo(
      id INTEGER PRIMARY KEY,name_display TEXT,symbol TEXT,isin TEXT,listing_date TEXT,
      status TEXT,is_mainboard BOOLEAN,created_at TEXT);
      CREATE TABLE ipo_issue(ipo_id INTEGER,issue_price NUMERIC,band_lo NUMERIC,band_hi NUMERIC);
      INSERT INTO ipo VALUES
        (11,'Cube Highways Trust','CUBEINVIT',NULL,'2026-08-01','listed',FALSE,'2026-01-01'),
        (12,'Equity Listed','EQUITY',NULL,'2026-08-01','listed',TRUE,'2026-01-01'),
        (13,'Equity Upcoming','UPCOMING',NULL,NULL,'announced',TRUE,'2026-08-01');""")
    class CursorAdapter:
        def __init__(self, cursor): self.cursor = cursor
        def execute(self, sql, params=()):
            values = tuple(value.isoformat() if isinstance(value, dt.date) else value for value in params)
            return self.cursor.execute(sql.replace("%s", "?"), values)
        def fetchall(self): return self.cursor.fetchall()
    class SchemaConn:
        def cursor(self): return CursorAdapter(raw.cursor())
    today = dt.date(2026, 8, 17)
    assert [row[0] for row in select_isin_candidates(SchemaConn(), today, 10)] == [12]
    assert [row[0] for row in select_listing_date_candidates(SchemaConn(), 10)] == [13]
    raw.close()


CSV = "SYMBOL,NAME OF COMPANY,DATE OF LISTING,ISIN NUMBER\nEXACT,ARDEE INDUSTRIES LIMITED,11-Aug-2026,INE000000001\nMISMATCH,Other Limited,12-Aug-2026,INE000000002\n"


class Response:
    def __init__(self, content=b"", payload=None, status=200): self.content,self.payload,self.status_code=content,payload,status
    def raise_for_status(self):
        if self.status_code != 200: raise RuntimeError(self.status_code)
    def json(self): return self.payload


def test_csv_fixture_exact_outcomes_name_guard_and_dry_run_no_mutation():
    headers, rows = parse_equity_master(CSV)
    assert headers == ["SYMBOL", "NAME OF COMPANY", "DATE OF LISTING", "ISIN NUMBER"]
    conn = Conn([(1,"Ardee Industries Ltd","EXACT",None,dt.date(2026,8,11)),
                 (2,"Entirely Different Company","MISMATCH",None,dt.date(2026,8,11)), None])
    session = Mock(); session.get.return_value = Response(CSV.encode())
    result = refresh(conn, session, limit=2, quote_limit=0, write=False, today=dt.date(2026,8,11))
    assert [r["outcome"] for r in result["rows"]] == ["would_update", "name_mismatch"]
    assert conn.commits == 0 and not any(sql.startswith("UPDATE") for sql, _ in conn.cur.executed)


def test_quote_fallback_exact_symbol_and_same_name_guard():
    assert quote_record({"meta":{"symbol":"OTHER","isin":"I"},"info":{"companyName":"Exact Limited"}}, "EXACT") is None
    conn = Conn([(1,"Exact Limited","EXACT",None,dt.date(2026,8,11))])
    session = Mock(); session.get.side_effect = [Response(b"SYMBOL,NAME OF COMPANY\n"),
        Response(payload={"meta":{"symbol":"EXACT","isin":"INE000000001"},
                          "info":{"companyName":"Different Limited"}})]
    result = refresh(conn, session, limit=1, quote_limit=1, write=False, today=dt.date(2026,8,11))
    assert result["quote_calls"] == 1 and result["rows"][0]["outcome"] == "name_mismatch"


def test_reserved_quota_prevents_persistent_isin_misses_starving_listing_date():
    old = [(n, f"Old {n} Ltd", f"OLD{n}", None, dt.date(2026,1,1)) for n in range(1, 6)]
    announced = [(99, "New Listing Ltd", "NEWLIST", "INE000000099", None)]
    conn = RoutedConn(old, announced)
    session = Mock(); session.get.return_value = Response(
        b"SYMBOL,NAME OF COMPANY,DATE OF LISTING,ISIN NUMBER\nNEWLIST,New Listing Limited,20-Aug-2026,INE000000099\n")
    result = refresh(conn, session, limit=6, quote_limit=0, write=False, today=dt.date(2026,8,11))
    assert result["selected"] == 4
    assert any(row["ipo_id"] == 99 and row["fields"] == ["listing_date"] for row in result["rows"])


def test_isin_owner_collision_and_invalid_isin_fail_closed_and_continue():
    candidates = [(10,"Alpha Ltd","ALPHA",None,dt.date(2026,8,11)),
                  (11,"Beta Ltd","BETA",None,dt.date(2026,8,11))]
    conn = RoutedConn(candidates, [], owners=[(77,)])
    csv_body = ("SYMBOL,NAME OF COMPANY,DATE OF LISTING,ISIN NUMBER\n"
                "ALPHA,Alpha Limited,11-Aug-2026,INE000000001\n"
                "BETA,Beta Limited,11-Aug-2026,not-an-isin\n").encode()
    session = Mock(); session.get.return_value = Response(csv_body)
    result = refresh(conn, session, limit=4, quote_limit=0, write=True, today=dt.date(2026,8,11))
    assert result["rows"][0]["outcome"] == "isin_owner_conflict"
    assert result["rows"][0]["candidate_ipo_id"] == 10 and result["rows"][0]["owner_ipo_id"] == 77
    assert result["rows"][1]["outcome"] == "invalid_isin"
    assert not any(sql.startswith("UPDATE") for sql, _ in conn.cur.executed)


def test_fill_empty_is_coalesce_guarded_and_budget_prints_before_work(capsys):
    conn = Conn(); conn.cur.rowcount = 0
    assert not _fill_empty(conn, 1, "isin", "INE000000001", write=True)
    sql = conn.cur.executed[0][0]
    assert "isin=COALESCE(isin, %s)" in sql and "isin IS NULL" in sql
    fake = Mock(); fake.close = Mock()
    with patch.dict("os.environ", {"DATABASE_URL": "postgresql://offline"}), \
         patch("psycopg2.connect", return_value=fake), patch("nse_fetch.prime", return_value=Mock()), \
         patch("nse_identity_backfill.refresh", return_value={"selected": 0}):
        backfill_main(["--dry-run", "--limit", "4", "--quote-limit", "2"])
    first = capsys.readouterr().out.splitlines()[0]
    assert first.startswith("OPERATIONS_BUDGET ")
    assert '"max_csv_calls": 1' in first and '"max_quote_calls": 2' in first
    assert '"max_selected_rows": 4' in first and '"max_updates": 8' in first
    with patch("fill_v2.log_source_fact"):
        try: _fill_empty(conn, 1, "status", "bad", write=True)
        except AssertionError: pass
        else: raise AssertionError("field allowlist did not fail closed")


def test_primary_source_non_200_raises_source_unavailable():
    # A 403/5xx from EQUITY_L.csv is a bounded, recoverable condition, surfaced as a
    # typed SourceUnavailable so the entry point can distinguish it from a real fault.
    from nse_identity_backfill import SourceUnavailable
    conn = Conn([(1, "Ardee Industries Ltd", "EXACT", None, dt.date(2026, 8, 11)), None])
    session = Mock(); session.get.return_value = Response(b"", status=403)
    try:
        refresh(conn, session, limit=1, quote_limit=0, write=False, today=dt.date(2026, 8, 11))
    except SourceUnavailable as exc:
        assert "403" in str(exc)
        assert exc.result["rows"][0]["outcome"] == "source_unavailable"
        assert "elapsed_ms" in exc.result["rows"][0]
    else:
        raise AssertionError("non-200 primary source must raise SourceUnavailable")
    assert conn.commits == 0  # nothing written on an unavailable source


def test_source_unavailable_is_a_clean_no_op_that_exits_zero(capsys):
    # main() must NOT raise (process exit 0) when the source is unavailable: a nightly
    # run that reaches the lane and fills nothing is a no-op, not a job failure. The
    # skip is still visible in the run log, and the connection is always released.
    from nse_identity_backfill import SourceUnavailable
    fake = Mock(); fake.close = Mock()
    with patch.dict("os.environ", {"DATABASE_URL": "postgresql://offline"}), \
         patch("psycopg2.connect", return_value=fake), \
         patch("nse_fetch.prime", return_value=Mock()), \
         patch("nse_identity_backfill.refresh",
               side_effect=SourceUnavailable("EQUITY_L.csv returned HTTP 403")):
        result = backfill_main(["--dry-run", "--limit", "4", "--quote-limit", "2"])
    assert result["status"] == "skipped"
    assert result["reason"] == "source_unavailable" and "403" in result["evidence"]["detail"]
    out = capsys.readouterr().out
    assert '"status": "skipped"' in out  # visible, not a fabricated zero measurement
    fake.close.assert_called_once()  # connection released on the no-op path


def test_prime_transport_failure_is_clean_skip_but_programming_error_is_nonzero(capsys):
    fake = Mock(); fake.close = Mock()
    common = (patch.dict("os.environ", {"DATABASE_URL": "postgresql://offline"}),
              patch("psycopg2.connect", return_value=fake))
    with common[0], common[1], patch("nse_fetch.prime", side_effect=TimeoutError("timed out")):
        result = backfill_main(["--dry-run"])
    assert result["status"] == "skipped" and result["reason"] == "source_unavailable"
    assert "timed out" not in capsys.readouterr().out

    fake = Mock(); fake.close = Mock()
    with patch.dict("os.environ", {"DATABASE_URL": "postgresql://offline"}), \
         patch("psycopg2.connect", return_value=fake), \
         patch("nse_fetch.prime", side_effect=ValueError("programming sentinel")):
        try: backfill_main(["--dry-run"])
        except RuntimeError as exc: assert str(exc) == "backfill_failed"
        else: raise AssertionError("programming errors must exit non-zero")
    output = capsys.readouterr().out
    assert "programming sentinel" not in output and '"reason": "backfill_failed"' in output


def test_real_fault_still_exits_non_zero(capsys):
    # A genuine fault (here a DB/driver error raised inside refresh) is NOT swallowed:
    # it propagates so the process exits non-zero. Only SourceUnavailable is a no-op.
    fake = Mock(); fake.close = Mock()
    with patch.dict("os.environ", {"DATABASE_URL": "postgresql://offline"}), \
         patch("psycopg2.connect", return_value=fake), \
         patch("nse_fetch.prime", return_value=Mock()), \
         patch("nse_identity_backfill.refresh", side_effect=RuntimeError("connection reset")):
        try:
            backfill_main(["--dry-run", "--limit", "4", "--quote-limit", "2"])
        except RuntimeError as exc:
            assert str(exc) == "backfill_failed"
        else:
            raise AssertionError("a real fault must propagate (non-zero exit)")
    fake.close.assert_called_once()  # connection still released via finally


def test_cron_and_capture_workflow_have_structural_handshake_order():
    cron = Path("pipeline/cron.py").read_text()
    assert cron.index('2c. NSE discovery') < cron.index('2d. bounded NSE identity') < cron.index('2e/2f. SBI ingest') < cron.index('3. NSE per-IPO lifecycle')
    workflow = Path(".github/workflows/preopen-capture.yml").read_text()
    assert workflow.count("python nse_identity_backfill.py") == 1
    assert 'cron: "20 3 * * 1-5"' in workflow
    assert "continue-on-error: true" in workflow
    assert "&& '--dry-run' || '--write'" in workflow
    capture = workflow.split("  capture:", 1)[1]
    assert "nse_identity_backfill.py" not in capture
    assert "20 3 * * 1-5" in capture


def test_quote_unavailable_classes_are_not_not_found_and_have_no_retry():
    row = (1, "Exact Limited", "EXACT", None, dt.date(2026, 8, 11))
    for response in (Response(status=429), Response(status=503)):
        conn = RoutedConn([row], [])
        session = Mock(); session.get.side_effect = [Response(b"SYMBOL,NAME OF COMPANY\n"), response]
        result = refresh(conn, session, limit=1, quote_limit=1, write=False)
        assert result["rows"][0]["outcome"] == "source_unavailable"
        assert session.get.call_count == 2
    conn = RoutedConn([row], [])
    session = Mock(); session.get.side_effect = [Response(b"SYMBOL,NAME OF COMPANY\n"), TimeoutError("secret")]
    result = refresh(conn, session, limit=1, quote_limit=1, write=False)
    assert result["rows"][0]["outcome"] == "source_unavailable"
    assert session.get.call_count == 2


def test_csv_and_quote_transport_failures_never_write_or_commit():
    row = (1, "Exact Limited", "EXACT", None, dt.date(2026, 8, 11))
    csv_conn = RoutedConn([row], [])
    csv_session = Mock(); csv_session.get.side_effect = TimeoutError("csv timeout")
    from nse_identity_backfill import SourceUnavailable
    try: refresh(csv_conn, csv_session, limit=1, quote_limit=1, write=True)
    except SourceUnavailable: pass
    else: raise AssertionError("CSV timeout must be source unavailable")
    assert csv_conn.commits == 0
    assert not any(sql.startswith("UPDATE") for sql, _ in csv_conn.cur.executed)

    quote_conn = RoutedConn([row], [])
    quote_session = Mock(); quote_session.get.side_effect = [
        Response(b"SYMBOL,NAME OF COMPANY\n"), TimeoutError("quote timeout")]
    result = refresh(quote_conn, quote_session, limit=1, quote_limit=1, write=True)
    assert result["rows"][0]["outcome"] == "source_unavailable"
    assert quote_conn.commits == 0
    assert not any(sql.startswith("UPDATE") for sql, _ in quote_conn.cur.executed)


def test_csv_and_quote_programming_errors_are_sanitized_nonzero_failures(capsys):
    cases = [
        (RoutedConn([], []), Mock(get=Mock(side_effect=TypeError("csv programming sentinel")))),
        (RoutedConn([(1, "Exact Limited", "EXACT", None, dt.date(2026, 8, 11))], []),
         Mock(get=Mock(side_effect=[Response(b"SYMBOL,NAME OF COMPANY\n"),
                                   AttributeError("quote programming sentinel")]))),
    ]
    for conn, session in cases:
        with patch.dict("os.environ", {"DATABASE_URL": "postgresql://offline"}), \
             patch("psycopg2.connect", return_value=conn), \
             patch("nse_fetch.prime", return_value=session):
            try: backfill_main(["--write", "--limit", "1", "--quote-limit", "1"])
            except RuntimeError as exc: assert str(exc) == "backfill_failed"
            else: raise AssertionError("programming errors must exit non-zero")
        assert conn.commits == 0 and conn.rollbacks >= 1
        assert not any(sql.startswith("UPDATE") for sql, _ in conn.cur.executed)
    output = capsys.readouterr().out
    assert "programming sentinel" not in output
    assert output.count('"reason": "backfill_failed"') == 2


def test_quote_quota_wrong_symbol_and_invalid_json_are_distinct():
    row = (1, "Exact Limited", "EXACT", None, dt.date(2026, 8, 11))
    conn = RoutedConn([row], []); session = Mock()
    session.get.return_value = Response(b"SYMBOL,NAME OF COMPANY\n")
    assert refresh(conn, session, limit=1, quote_limit=0)["rows"][0]["outcome"] == "not_attempted_quote_quota"
    conn = RoutedConn([row], []); session = Mock()
    session.get.side_effect = [Response(b"SYMBOL,NAME OF COMPANY\n"),
        Response(payload={"meta": {"symbol": "OTHER"}, "info": {"companyName": "Exact Limited"}})]
    assert refresh(conn, session, limit=1, quote_limit=1)["rows"][0]["outcome"] == "exact_symbol_mismatch"
    conn = RoutedConn([row], []); bad = Response(); bad.json = Mock(side_effect=ValueError("bad"))
    session = Mock(); session.get.side_effect = [Response(b"SYMBOL,NAME OF COMPANY\n"), bad]
    assert refresh(conn, session, limit=1, quote_limit=1)["rows"][0]["outcome"] == "invalid_response"


def test_deadline_stops_later_quotes_and_every_symbol_has_elapsed_record():
    rows = [(1, "One Limited", "ONE", None, dt.date(2026, 8, 11)),
            (2, "Two Limited", "TWO", None, dt.date(2026, 8, 11))]
    now = [0.0]
    clock = lambda: now[0]
    conn = RoutedConn(rows, []); session = Mock()
    def get(url, **kwargs):
        if "EQUITY_L" in url: return Response(b"SYMBOL,NAME OF COMPANY\n")
        now[0] = 1.1
        return Response(status=503)
    session.get.side_effect = get
    result = refresh(conn, session, limit=3, quote_limit=2, deadline=1.0, clock=clock)
    assert session.get.call_count == 2
    assert result["rows"][1]["outcome"] == "not_attempted_deadline"
    assert all("elapsed_ms" in row and row["outcome"] for row in result["rows"])


def test_one_quote_failure_does_not_discard_later_valid_result():
    rows = [(1, "One Limited", "ONE", None, dt.date(2026, 8, 11)),
            (2, "Two Limited", "TWO", None, dt.date(2026, 8, 11))]
    conn = RoutedConn(rows, []); session = Mock()
    session.get.side_effect = [Response(b"SYMBOL,NAME OF COMPANY\n"), TimeoutError(),
        Response(payload={"meta": {"symbol": "TWO", "isin": "INE000000002"},
                          "info": {"companyName": "Two Limited"}})]
    result = refresh(conn, session, limit=3, quote_limit=2, write=False)
    assert [r["outcome"] for r in result["rows"]] == ["source_unavailable", "would_update"]


def test_source_fact_failure_rolls_back_field_update():
    conn = Conn(); conn.cur.rowcount = 1
    with patch("fill_v2.log_source_fact", side_effect=RuntimeError("fact failed")):
        try: _fill_empty(conn, 1, "isin", "INE000000001", write=True)
        except RuntimeError: pass
        else: raise AssertionError("source-fact failure must propagate")
    assert conn.rollbacks == 1 and conn.commits == 0


def test_final_commit_failure_is_sanitized_visible_and_rolls_back():
    row = (1, "Exact Limited", "EXACT", None, dt.date(2026, 8, 11))
    conn = RoutedConn([row], []); conn.commit = Mock(side_effect=RuntimeError("dsn secret"))
    conn.cur.rowcount = 1
    session = Mock(); session.get.side_effect = [
        Response(b"SYMBOL,NAME OF COMPANY,DATE OF LISTING,ISIN NUMBER\n"
                 b"EXACT,Exact Limited,11-Aug-2026,INE000000001\n")]
    with patch("fill_v2.log_source_fact"):
        try: refresh(conn, session, limit=1, write=True)
        except RuntimeError as exc: assert str(exc) == "final_commit_failed"
        else: raise AssertionError("commit failure must propagate")
    assert conn.rollbacks == 1


def test_main_uses_finite_db_policy_and_redacts_connection_failure(capsys):
    secret = "postgresql://user:password@private/db?token=abc"
    with patch.dict("os.environ", {"DATABASE_URL": secret}), \
         patch("psycopg2.connect", side_effect=RuntimeError(secret)) as connect:
        try: backfill_main(["--dry-run", "--max-runtime-seconds", "240"])
        except RuntimeError as exc: assert str(exc) == "db_connect_failed"
        else: raise AssertionError("connect failure must propagate")
    kwargs = connect.call_args.kwargs
    assert kwargs == {"connect_timeout": DB_CONNECT_TIMEOUT, "keepalives": 1,
                      "keepalives_idle": 30, "keepalives_interval": 10, "keepalives_count": 3}
    assert "options" not in kwargs
    output = capsys.readouterr().out
    assert secret not in output and "password" not in output and "token=abc" not in output


def test_session_timeouts_are_set_before_source_work():
    events = []
    conn = Mock()
    conn.cursor.return_value.execute.side_effect = lambda sql, _params: events.append(sql)
    def primed(*_args, **_kwargs):
        events.append("prime")
        return Mock()
    with patch.dict("os.environ", {"DATABASE_URL": "postgresql://offline"}), \
         patch("psycopg2.connect", return_value=conn), \
         patch("nse_fetch.prime", side_effect=primed), \
         patch("nse_identity_backfill.refresh", return_value={"selected": 0}):
        backfill_main(["--dry-run"])
    assert events[:3] == ["SET statement_timeout = %s", "SET lock_timeout = %s", "prime"]


def test_session_timeout_configuration_failure_is_nonzero_before_network_or_writes(capsys):
    for failing_sql in ("SET statement_timeout = %s", "SET lock_timeout = %s"):
        executed = []
        conn = Mock()
        def execute(sql, _params):
            executed.append(sql)
            if sql == failing_sql:
                raise RuntimeError("configuration sentinel")
        conn.cursor.return_value.execute.side_effect = execute
        with patch.dict("os.environ", {"DATABASE_URL": "postgresql://offline"}), \
             patch("psycopg2.connect", return_value=conn), \
             patch("nse_fetch.prime") as prime:
            try: backfill_main(["--write"])
            except RuntimeError as exc: assert str(exc) == "backfill_failed"
            else: raise AssertionError("session timeout configuration failure must be non-zero")
        prime.assert_not_called()
        conn.commit.assert_not_called()
        assert not any(sql.startswith("UPDATE") for sql in executed)
        conn.rollback.assert_called_once()
        conn.close.assert_called_once()
    output = capsys.readouterr().out
    assert "configuration sentinel" not in output
    assert output.count('"reason": "backfill_failed"') == 2
