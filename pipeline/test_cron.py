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
    assert "verified by publish_snapshot_with_ledger output" in output
    assert "SBI ingest/extraction" in output and "NSE discovery" in output


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
