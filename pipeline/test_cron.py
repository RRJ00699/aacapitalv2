import importlib.util
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("daily_cron", HERE / "cron.py")
cron = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cron)


def test_no_argument_is_live_default():
    args = cron.parse_args([])
    assert not args.dry_run


def test_missing_database_url_is_single_stop_message(capsys):
    assert cron.environment_preflight({}) is False
    output = capsys.readouterr().out
    assert output.count("STOP:") == 1
    assert output.rstrip().endswith("STOP: required environment variable absent: DATABASE_URL")


def test_preflight_redacts_secret_values(capsys):
    sentinel = "never-print-this-value"
    assert cron.environment_preflight({"DATABASE_URL": sentinel}) is True
    output = capsys.readouterr().out
    assert sentinel not in output
    assert "DATABASE_URL" in output and "present" in output


def test_optional_configuration_classifies_absent_names(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    ready, missing = cron.configured(("ANTHROPIC_API_KEY",))
    assert not ready and missing == ["ANTHROPIC_API_KEY"]
    assert cron.skip("paid", "owner: configure ANTHROPIC_API_KEY")["status"] == "skipped"


def test_kite_proxy_is_conditional_on_rotation():
    base = {name: "configured" for name in
            ("KITE_API_KEY", "KITE_API_SECRET", "KITE_USER_ID", "KITE_PASSWORD", "KITE_TOTP_SECRET")}
    assert cron.kite_configuration(base) == (True, [], [])
    base["EXECUTE_CLOUDFLARE_SECRET_ROTATION"] = "1"
    ready, missing, rotation = cron.kite_configuration(base)
    assert ready and not missing
    assert rotation == ["KITE_BROKER_PROXY_URL", "KITE_BROKER_PROXY_AUTH_SECRET"]


def test_preflight_inventories_required_owner_kite_handoff_pair():
    names = {row[0] for row in cron.ENVIRONMENT}
    assert {"ALLOW_LEGACY_KITE_DB_TOKEN_WRITE", "KITE_REFRESH_VALIDATE_ONLY"} <= names


def test_structured_counts_are_real_and_missing_contract_fails():
    discovery = {"output": '{"DISCOVERY":{"returned_count":5,"errors":[],"discovered_ipos":'
                           '[{"resolution":"matched_existing"},{"resolution":"inserted"},'
                           '{"resolution":"bootstrap_required"},{"resolution":"bounded_not_created"}]}}', "status": "ok"}
    assert cron.discovery_counts(discovery) == {"returned": 5, "processed": 4,
        "matched_existing": 1, "created": 1, "would_create": 1,
        "bounded_not_created": 1, "failures": 0}
    broken = {"output": "not structured", "status": "ok"}
    assert cron.discovery_counts(broken) == {"returned": 0, "processed": 0,
        "matched_existing": 0, "created": 0, "would_create": 0,
        "bounded_not_created": 0, "failures": 0}
    assert broken["status"] == "failed"


def test_kite_fetch_requires_structured_refresh_success():
    assert not cron.kite_refresh_guarantees_fetch("skipped", "SKIPPED_NOT_ACTIVATED")
    assert not cron.kite_refresh_guarantees_fetch("failed", "FAILED_LOGIN")
    assert cron.kite_refresh_guarantees_fetch("ok", "SUCCESS_ROTATED")
    assert not cron.kite_refresh_guarantees_fetch("skipped", "SUCCESS_VALIDATED_ONLY")
    assert cron.kite_refresh_guarantees_fetch("ok", "SUCCESS_VALIDATED_HANDED_OFF")


@pytest.mark.parametrize("refresh_status,marker,expected_calls", [
    ("skipped", "SKIPPED_NOT_ACTIVATED", [cron.KITE_REFRESH_SCRIPT]),
    ("failed", "FAILED_LOGIN", [cron.KITE_REFRESH_SCRIPT]),
    ("ok", "SUCCESS_ROTATED", [cron.KITE_REFRESH_SCRIPT, cron.KITE_FETCH_SCRIPT,
                                  cron.KITE_FETCH_15M_SCRIPT, cron.TOP_DETECTOR_SCRIPT]),
])
def test_kite_live_handshake_blocks_or_allows_fetch(monkeypatch, refresh_status, marker, expected_calls):
    calls = []
    def fake_run(step, target, args, **kwargs):
        calls.append(target)
        if target == cron.KITE_REFRESH_SCRIPT:
            rc = 1 if refresh_status == "failed" else 0
            return {"step": step, "status": refresh_status, "duration": 0,
                    "rc": rc, "output": f"KITE_REFRESH_STATUS={marker}\n"}
        marker_output = ({cron.KITE_FETCH_15M_SCRIPT:
                          'FIFTEEN_MIN_CANDLES={"selected":1}',
                          cron.KITE_FETCH_SCRIPT:
                          'KITE_DAILY_SUMMARY={"selected":1,"token_resolved":1,"token_unresolved":0,"failed":0}',
                          cron.TOP_DETECTOR_SCRIPT:
                          'TOP_DETECTOR={"selected":1,"state_counts":{}}'}
                         .get(target, ""))
        return {"step": step, "status": "ok", "duration": 0,
                "output": marker_output}
    monkeypatch.setattr(cron, "run", fake_run)
    results = cron.run_kite_live("12", [])
    assert calls == expected_calls
    assert results[-1]["status"] == ("ok" if refresh_status == "ok" else "skipped")


def test_every_subprocess_target_is_repository_relative_and_visible():
    targets = [cron.RHP_DOWNLOAD_SCRIPT, cron.SBI_DOWNLOAD_SCRIPT, cron.KITE_REFRESH_SCRIPT,
               cron.NSE_LIFECYCLE_SCRIPT, cron.NSE_IDENTITY_SCRIPT, cron.KITE_FETCH_SCRIPT,
               cron.KITE_FETCH_15M_SCRIPT, cron.TOP_DETECTOR_SCRIPT,
               cron.DRIVE_SCRIPT, cron.SNAPSHOT_PUBLISH_SCRIPT]
    assert all(not Path(target).is_absolute() and (cron.REPO_ROOT / target).is_file() for target in targets)


def test_run_uses_absolute_python_script_and_explicit_cwd(monkeypatch, tmp_path):
    child = tmp_path / "child.py"
    child.write_text("print('ok')", encoding="utf-8")
    seen = {}
    def fake_run(cmd, **kwargs):
        seen.update(cmd=cmd, kwargs=kwargs)
        return subprocess.CompletedProcess(cmd, 0, "ok\n", "")
    monkeypatch.setattr(cron.subprocess, "run", fake_run)
    result = cron.run("child", child, [], cwd=tmp_path)
    assert result["status"] == "ok"
    assert seen["cmd"][0] == sys.executable
    assert Path(seen["cmd"][1]).is_absolute()
    assert Path(seen["kwargs"]["cwd"]).is_absolute()
    assert seen["kwargs"]["env"]["PYTHONIOENCODING"] == "utf-8"


def test_missing_required_script_is_failure(tmp_path):
    result = cron.run("required", tmp_path / "absent.py", [])
    assert result["status"] == "failed"


def test_zero_target_report_has_timings_counts_and_snapshot_proof(capsys, monkeypatch):
    monkeypatch.setattr(cron.time, "monotonic", lambda: 12.5)
    steps = [
        {"step": "active IPO processing", "status": "skipped", "duration": 0.0,
         "reason": "no active IPOs selected"},
        {"step": "snapshot publication consumer proof", "status": "ok", "duration": 1.2},
    ]
    assert cron.report(steps, 10.0, dry=False, targets=[], cap=2, spent=0) == 0
    output = capsys.readouterr().out
    assert "END-OF-RUN REPORT" in output
    assert "runtime: 2.5s" in output
    assert "active pipeline IPOs: 0 | market IPOs: 0" in output
    assert "consumer_source=active" in output


def test_failed_step_controls_final_exit_code(monkeypatch):
    monkeypatch.setattr(cron.time, "monotonic", lambda: 1.0)
    assert cron.report([{"step": "x", "status": "failed", "duration": 0.1}], 0,
                       dry=True, targets=[]) == 1


def test_db_measurement_failure_retains_and_prints_twelve_line_traceback(monkeypatch, capsys):
    steps = []
    def fail(_conn):
        def nested():
            raise cron.psycopg2.OperationalError("could not translate host name")
        nested()
    monkeypatch.setattr(cron, "db", lambda: SimpleNamespace(close=lambda: None))
    value, ok = cron.measure_db(steps, "Pre-run V2 completeness plan", fail, [])
    assert value == [] and not ok
    assert steps[0]["status"] == "failed"
    assert len(steps[0]["traceback_tail"].splitlines()) <= 12
    assert "OperationalError" in steps[0]["traceback_tail"]
    assert "traceback tail:" in capsys.readouterr().out


def test_successful_zero_spend_is_not_measurement_failure(monkeypatch):
    class ZeroCursor:
        def execute(self, *_args):
            pass
        def fetchone(self):
            return (0,)
    connection = SimpleNamespace(cursor=lambda: ZeroCursor(), close=lambda: None)
    monkeypatch.setattr(cron, "db", lambda: connection)
    steps = []
    value, available = cron.measure_db(steps, "Spend before measurement",
                                       cron.spent_today, None)
    assert value == 0.0
    assert available
    assert steps == []


@pytest.mark.parametrize("failed_measurement", [cron.get_cap, cron.spent_today])
def test_spend_query_failure_skips_paid_subprocess(monkeypatch, capsys, failed_measurement):
    monkeypatch.setenv("DATABASE_URL", "redacted")
    monkeypatch.setenv("RHP_EXTRACTION_OWNER_APPROVED", "YES")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "configured")
    calls = []

    def fake_run(step, target, args, **_kwargs):
        calls.append((step, target, args))
        return {"step": step, "status": "ok", "duration": 0.0, "output": ""}

    def fake_with_db(fn, *_args, **_kwargs):
        if fn is cron.select_active:
            return [(7, "Seven", None)], "ACTIVE"
        if fn is cron.completeness_plan:
            return []
        if fn is failed_measurement:
            raise cron.psycopg2.OperationalError("spend query unavailable")
        if fn is cron.get_cap:
            return 2.0
        if fn is cron.spent_today:
            return 0.0
        raise AssertionError(fn)

    monkeypatch.setattr(cron, "run", fake_run)
    monkeypatch.setattr(cron, "with_db_read_retry", fake_with_db)
    rc = cron.main(["--skip-download", "--skip-kite"])
    output = capsys.readouterr().out
    paid_calls = [call for call in calls if call[0] == "RHP paid extraction"]
    assert paid_calls == []
    assert "spend query unavailable" in output
    assert "paid execution disabled: spend measurement unavailable" in output
    assert "END-OF-RUN REPORT" in output
    assert rc == 1


def test_select_active_operational_error_reaches_end_of_run_without_uncaught_traceback(
        monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "redacted")
    monkeypatch.setattr(cron, "environment_preflight", lambda: True)
    monkeypatch.setattr(cron, "run", lambda step, *_args, **_kwargs:
                        {"step": step, "status": "failed", "duration": 0.0,
                         "reason": "test child disabled"})
    def measured(fn, *_args, **_kwargs):
        if fn is cron.select_active:
            raise cron.psycopg2.OperationalError("DNS unavailable")
        if fn is cron.get_cap:
            return 2.0
        if fn is cron.spent_today:
            return 0.0
        raise AssertionError(fn)
    monkeypatch.setattr(cron, "with_db", measured)
    rc = cron.main(["--dry-run"])
    output = capsys.readouterr().out
    assert rc == 1
    assert "Active IPO selector = failed" in output
    assert "selector failed; dependent cohort work skipped" in output
    assert "no active IPOs selected" not in output
    assert "active pipeline IPOs: UNKNOWN — selector failed" in output
    assert "END-OF-RUN REPORT" in output


@pytest.mark.parametrize("cwd", [cron.REPO_ROOT, Path("/")])
def test_entrypoint_from_any_working_directory_stops_cleanly_without_database(cwd):
    env = os.environ.copy()
    env.pop("DATABASE_URL", None)
    completed = subprocess.run([sys.executable, str(HERE / "cron.py"), "--dry-run"],
                               cwd=cwd, env=env, text=True, capture_output=True)
    assert completed.returncode == 2
    assert completed.stdout.rstrip().endswith("STOP: required environment variable absent: DATABASE_URL")


def test_db_retries_transient_connect_failures_then_succeeds(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://offline")
    calls = {"n": 0}
    def flaky(dsn, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise cron.psycopg2.OperationalError("could not translate host name (DNS)")
        return "CONN"
    monkeypatch.setattr(cron.psycopg2, "connect", flaky)
    slept = []
    conn = cron.db(attempts=4, base_delay=0.01, sleep=slept.append)
    assert conn == "CONN" and calls["n"] == 3 and len(slept) == 2  # backed off twice


def test_db_raises_after_exhausting_retries(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://offline")
    def always_fail(dsn, **kwargs):
        raise cron.psycopg2.OperationalError("dns down")
    monkeypatch.setattr(cron.psycopg2, "connect", always_fail)
    with pytest.raises(cron.psycopg2.OperationalError):
        cron.db(attempts=2, base_delay=0.0, sleep=lambda s: None)


def test_with_db_does_not_retry_callback_and_always_closes(monkeypatch):
    conns = []
    class FakeConn:
        def __init__(self): self.closed = False
        def close(self): self.closed = True
    monkeypatch.setattr(cron, "db", lambda **k: conns.append(FakeConn()) or conns[-1])
    calls = {"n": 0}
    def fn(conn):
        calls["n"] += 1
        if calls["n"] == 1:
            raise cron.psycopg2.OperationalError("server closed the connection unexpectedly")
        return "OK"
    with pytest.raises(cron.psycopg2.OperationalError):
        cron.with_db(fn)
    assert calls["n"] == 1 and len(conns) == 1
    assert conns[0].closed


def test_sbi_writer_cannot_be_callback_retried(monkeypatch):
    calls = []
    monkeypatch.setattr(cron, "db", lambda: SimpleNamespace(close=lambda: None))
    def run_sbi_lane(_conn):
        calls.append(1)
        raise cron.psycopg2.OperationalError("ambiguous commit")
    with pytest.raises(cron.psycopg2.OperationalError):
        cron.with_db(run_sbi_lane)
    assert calls == [1]


def test_read_retry_uses_fresh_closed_connections_and_measurement_is_available(monkeypatch):
    conns = []
    class Conn:
        def __init__(self): self.closed = False
        def close(self): self.closed = True
    monkeypatch.setattr(cron, "db", lambda: conns.append(Conn()) or conns[-1])
    calls = []
    def measurement(_conn):
        calls.append(1)
        if len(calls) == 1:
            raise cron.psycopg2.OperationalError("dead read session")
        return 0
    steps = []
    value, available = cron.measure_db(steps, "zero measurement", measurement, None)
    assert value == 0 and available and calls == [1, 1]
    assert len(conns) == 2 and all(conn.closed for conn in conns)
    assert steps == []


def test_partial_step_is_retry_required_and_nonzero(capsys, monkeypatch):
    monkeypatch.setattr(cron.time, "monotonic", lambda: 1)
    rc = cron.report([{"step":"SEBI", "status":"partial", "duration":0,
                       "reason":"RETRY_PENDING"}], 0, dry=False, targets=[])
    assert rc == 3
    assert "total status: partial/retry_required" in capsys.readouterr().out


def test_exhausted_sebi_backlog_is_owner_visible(capsys, monkeypatch):
    monkeypatch.setattr(cron.time, "monotonic", lambda: 1)
    step = {"step":"SEBI", "status":"partial", "duration":0,
            "reason":"PARTIAL", "owner_action":"owner: retry or resolve 2 exhausted SEBI filing(s)"}
    assert cron.report([step], 0, dry=False, targets=[]) == 3
    output = capsys.readouterr().out
    assert "owner actions still required: owner: retry or resolve 2 exhausted" in output


def _sebi_item(payload):
    return {"step": "SEBI RHP download", "status": "ok", "duration": 0,
            "output": "SEBI_DOWNLOAD_SUMMARY=" + __import__("json").dumps(payload)}


def test_healthy_bounded_sebi_progress_is_green_and_backlog_visible(capsys, monkeypatch):
    item = _sebi_item({"this_run":{"succeeded":4,"failed":0,"retries":0},
                       "backlog":{"pending":1033,"owner_action_exhausted":0},
                       "status":"RETRY_PENDING"})
    cron.attach_sebi_status(item)
    assert item["status"] == "ok" and item["reason"] == "ok/progress_pending"
    monkeypatch.setattr(cron.time, "monotonic", lambda: 1)
    assert cron.report([item], 0, dry=False, targets=[], market_targets=[]) == 0
    assert "backlog_pending=1033" in capsys.readouterr().out


@pytest.mark.parametrize("payload", [
    {"this_run":{"succeeded":3,"failed":1}, "backlog":{"pending":1}, "status":"PARTIAL"},
    {"this_run":{"succeeded":4,"failed":0},
     "backlog":{"pending":1,"owner_action_exhausted":1}, "status":"PARTIAL"},
])
def test_sebi_failure_or_exhaustion_remains_nonzero(payload, monkeypatch):
    item = _sebi_item(payload); cron.attach_sebi_status(item)
    monkeypatch.setattr(cron.time, "monotonic", lambda: 1)
    assert item["status"] == "partial"
    assert cron.report([item], 0, dry=False, targets=[], market_targets=[]) == 3


def test_empty_sebi_backlog_is_green_and_missing_summary_fails_closed():
    item = _sebi_item({"this_run":{"succeeded":0,"failed":0},
                       "backlog":{"pending":0,"owner_action_exhausted":0}, "status":"OK"})
    cron.attach_sebi_status(item); assert item["status"] == "ok"
    broken = {"status":"ok", "output":"", "step":"SEBI", "duration":0}
    cron.attach_sebi_status(broken); assert broken["status"] == "failed"


def test_market_selector_is_independent_listed_stale_first_cohort():
    class Cursor:
        def execute(self, sql, params):
            normalized = " ".join(sql.split())
            assert "i.listing_date IS NOT NULL" in normalized
            assert "NULLIF(trim(i.symbol),'') IS NOT NULL" in normalized
            assert "issue_size_cr" not in normalized
            assert "GREATEST(d.latest,m.latest) ASC NULLS FIRST" in normalized
            assert params == (cron.ACTIVE_DAYS, 2)
        def fetchall(self): return [(20,"Ardee",__import__("datetime").date.today()), (21,"Stale",__import__("datetime").date.today())]
    class Conn:
        def cursor(self): return Cursor()
    assert [row[0] for row in cron.select_market(Conn(), 2)] == [20, 21]


def test_runbook_path_and_commands_contract():
    text = (cron.REPO_ROOT / "docs/runbooks/DAILY_RUN.md").read_text(encoding="utf-8")
    assert "C:\\aacapital-v2" in text
    assert "python pipeline\\cron.py --dry-run" in text
    assert "python pipeline\\cron.py\n" in text
    assert len(text.splitlines()) <= 45
    assert "git switch main; git pull --ff-only origin main" in text
    assert "git reset --hard" not in text
    consumers = {name: consumer for name, consumer, _effect in cron.ENVIRONMENT}
    assert consumers["NTFY_TOPIC"] == "drive.py completeness alerts"
    assert consumers["RULE_VALIDATION_OWNER_APPROVED"] == "rule_validation_results writes"
    assert "ALLOW_LEGACY_KITE_DB_TOKEN_WRITE=1" in text
    assert "KITE_REFRESH_VALIDATE_ONLY=1" in text
