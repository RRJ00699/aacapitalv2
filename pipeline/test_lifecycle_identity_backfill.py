import datetime as dt
from pathlib import Path
from unittest.mock import Mock, patch

from nse_fetch import parse_discovery_item
from nse_identity_backfill import (parse_equity_master, quote_record, refresh,
    select_isin_candidates, select_listing_date_candidates, main as backfill_main,
    _fill_empty)
from nse_lifecycle import reconcile_discovery, report_transition_coverage


class Cursor:
    def __init__(self, rows=()): self.rows, self.executed, self.rowcount = iter(rows), [], 0
    def execute(self, sql, params=()): self.executed.append((" ".join(sql.split()), params))
    def fetchone(self): return next(self.rows)
    def fetchall(self): return list(self.rows)


class Conn:
    def __init__(self, rows=()): self.cur, self.commits, self.rollbacks = Cursor(rows), 0, 0
    def cursor(self): return self.cur
    def commit(self): self.commits += 1
    def rollback(self): self.rollbacks += 1


def discovery(name="New Limited", symbol="COLLIDE", isin=None, category="MAINBOARD"):
    return parse_discovery_item({"companyName": name, "symbol": symbol, "isin": isin,
        "category": category, "issueStartDate": "10-Aug-2026", "issueEndDate": "12-Aug-2026",
        "priceBand": "100-110", "lotSize": "10"})


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
    report = reconcile_discovery(conn, rows, write=False, max_new_rows=1)[0]
    assert len(report) == 3
    assert [r["resolution"] for r in report] == ["bootstrap_required", "bounded_not_created", "bounded_not_created"]


def test_selectors_are_bounded_and_encode_all_predicates():
    c = Conn([]); select_isin_candidates(c, dt.date(2026,8,11), 4)
    sql, params = c.cur.executed[0]
    assert "isin IS NULL" in sql and "symbol IS NOT NULL" in sql and "listing_date IS NOT NULL" in sql
    assert params == (dt.date(2026,8,12), 4)
    c = Conn([]); select_listing_date_candidates(c, 3); sql, params = c.cur.executed[0]
    assert "listing_date IS NULL" in sql and "symbol IS NOT NULL" in sql and "status='announced'" in sql
    assert params == (3,)


CSV = "SYMBOL,NAME OF COMPANY,DATE OF LISTING,ISIN NUMBER\nEXACT,Exact Limited,11-Aug-2026,INE000000001\nMISMATCH,Other Limited,12-Aug-2026,INE000000002\n"


class Response:
    def __init__(self, content=b"", payload=None, status=200): self.content,self.payload,self.status_code=content,payload,status
    def raise_for_status(self):
        if self.status_code != 200: raise RuntimeError(self.status_code)
    def json(self): return self.payload


def test_csv_fixture_exact_outcomes_name_guard_and_dry_run_no_mutation():
    headers, rows = parse_equity_master(CSV)
    assert headers == ["SYMBOL", "NAME OF COMPANY", "DATE OF LISTING", "ISIN NUMBER"]
    conn = Conn([(1,"Exact Limited","EXACT",None,dt.date(2026,8,11)),
                 (2,"Wrong Limited","MISMATCH",None,dt.date(2026,8,11))])
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


def test_transition_signal_only_after_both_exact_coverage_checks(capsys):
    missing = Conn([None]); discovered = [discovery("Covered Ltd", "COVER")]
    assert report_transition_coverage(missing, ["Ardee Industries Limited"], discovered)
    assert capsys.readouterr().out.strip() == "CLOSED_PRELISTING_SOURCE_MISSING company=Ardee Industries Limited action=owner_attention"
    existing = Conn([(1,)])
    assert report_transition_coverage(existing, ["Existing Ltd"], []) == []
    feed_only = Conn([None])
    assert report_transition_coverage(feed_only, ["Covered Ltd"], discovered) == []


def test_cron_and_capture_workflow_have_structural_handshake_order():
    cron = Path("pipeline/cron.py").read_text()
    assert cron.index('2c. NSE discovery') < cron.index('2d. bounded NSE identity') < cron.index('2e/2f. SBI ingest') < cron.index('3. NSE per-IPO lifecycle')
    workflow = Path(".github/workflows/preopen-capture.yml").read_text()
    backfill = "python nse_identity_backfill.py --write --limit 5 --quote-limit 5"
    assert workflow.count(backfill) == 1
    assert workflow.index(backfill) < workflow.index("python capture_preopen.py")
