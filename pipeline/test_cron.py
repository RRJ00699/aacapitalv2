import importlib.util
import os
from pathlib import Path
import subprocess
import sys

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
    secret = "never-print-this-value"
    assert cron.environment_preflight({"DATABASE_URL": secret}) is True
    output = capsys.readouterr().out
    assert secret not in output
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
    assert cron.kite_refresh_guarantees_fetch("ok", "SUCCESS_VALIDATED_ONLY")


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
    assert "active IPOs: 0" in output
    assert "consumer_source=active" in output


def test_failed_step_controls_final_exit_code(monkeypatch):
    monkeypatch.setattr(cron.time, "monotonic", lambda: 1.0)
    assert cron.report([{"step": "x", "status": "failed", "duration": 0.1}], 0,
                       dry=True, targets=[]) == 1


@pytest.mark.parametrize("cwd", [cron.REPO_ROOT, Path("/")])
def test_entrypoint_from_any_working_directory_stops_cleanly_without_database(cwd):
    env = os.environ.copy()
    env.pop("DATABASE_URL", None)
    completed = subprocess.run([sys.executable, str(HERE / "cron.py"), "--dry-run"],
                               cwd=cwd, env=env, text=True, capture_output=True)
    assert completed.returncode == 2
    assert completed.stdout.rstrip().endswith("STOP: required environment variable absent: DATABASE_URL")


def test_runbook_path_and_commands_contract():
    text = (cron.REPO_ROOT / "docs/runbooks/DAILY_RUN.md").read_text(encoding="utf-8")
    assert "C:\\aacapital-v2" in text
    assert "python pipeline\\cron.py --dry-run" in text
    assert "python pipeline\\cron.py\n" in text
    assert len(text.splitlines()) <= 45
    assert "git switch main; git pull --ff-only origin main" in text
    assert "git reset --hard" not in text
    assert "drive.py completeness alerts" in cron.ENVIRONMENT[-1][1]
    assert "ALLOW_LEGACY_KITE_DB_TOKEN_WRITE=1" in text
    assert "KITE_REFRESH_VALIDATE_ONLY=1" in text
