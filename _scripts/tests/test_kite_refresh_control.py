import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "_scripts" / "refresh_kite_token.py"


def load_refresh():
    spec = importlib.util.spec_from_file_location("kite_refresh_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def isolated_refresh_env(monkeypatch):
    for name in (
        "EXECUTE_CLOUDFLARE_SECRET_ROTATION", "ALLOW_LEGACY_KITE_DB_TOKEN_WRITE",
        "KITE_BROKER_PROXY_URL", "KITE_BROKER_PROXY_AUTH_SECRET",
        "KITE_REFRESH_VALIDATE_ONLY", "KITE_REFRESH_TEST_ROTATION",
        "KITE_REFRESH_TEST_VERIFICATION", "NTFY_TOPIC",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("KITE_REFRESH_TEST_MODE", "1")


def test_login_success_activation_disabled_is_skipped(capsys):
    refresh = load_refresh()
    assert refresh.main() == 0
    assert capsys.readouterr().out.strip() == "KITE_REFRESH_STATUS=SKIPPED_NOT_ACTIVATED"


def test_login_success_validate_only(monkeypatch, capsys):
    monkeypatch.setenv("KITE_REFRESH_VALIDATE_ONLY", "1")
    monkeypatch.setenv("KITE_REFRESH_TEST_VERIFICATION", "success")
    refresh = load_refresh()
    assert refresh.main() == 0
    assert capsys.readouterr().out.strip() == "KITE_REFRESH_STATUS=SUCCESS_VALIDATED_ONLY"


def test_missing_broker_config_fails_only_when_activated(monkeypatch, capsys):
    refresh = load_refresh()
    assert refresh.main() == 0
    assert "SKIPPED_NOT_ACTIVATED" in capsys.readouterr().out

    monkeypatch.setenv("EXECUTE_CLOUDFLARE_SECRET_ROTATION", "1")
    alerts = []
    monkeypatch.setattr(refresh, "_alert", alerts.append)
    assert refresh.main() == 1
    assert capsys.readouterr().out.strip() == "KITE_REFRESH_STATUS=FAILED_ROTATION"
    assert alerts


def activated(monkeypatch):
    monkeypatch.setenv("EXECUTE_CLOUDFLARE_SECRET_ROTATION", "1")
    monkeypatch.setenv("KITE_BROKER_PROXY_URL", "https://broker.invalid")
    monkeypatch.setenv("KITE_BROKER_PROXY_AUTH_SECRET", "test-auth-secret")


def test_rotation_failure_alerts_and_does_not_leak_token(monkeypatch, capsys, caplog):
    activated(monkeypatch)
    monkeypatch.setenv("KITE_REFRESH_TEST_ROTATION", "failure")
    refresh = load_refresh()
    alerts = []
    monkeypatch.setattr(refresh, "_alert", alerts.append)
    assert refresh.main() == 1
    captured = capsys.readouterr()
    combined = captured.out + captured.err + caplog.text + " ".join(alerts)
    assert "KITE_REFRESH_STATUS=FAILED_ROTATION" in combined
    assert alerts
    assert "test-only-sensitive-access-token" not in combined
    assert "test-on" not in combined


def test_login_diagnostics_do_not_log_request_ids_totp_or_redirects():
    source = SCRIPT.read_text(encoding="utf8")
    assert "request_id[:" not in source
    assert "Generated TOTP:" not in source
    assert "Redirect location:" not in source


def test_verification_failure_alerts_and_keeps_overlay_unavailable(monkeypatch, capsys):
    activated(monkeypatch)
    monkeypatch.setenv("KITE_REFRESH_TEST_ROTATION", "success")
    monkeypatch.setenv("KITE_REFRESH_TEST_VERIFICATION", "failure")
    refresh = load_refresh()
    alerts = []
    monkeypatch.setattr(refresh, "_alert", alerts.append)
    assert refresh.main() == 1
    assert capsys.readouterr().out.strip() == "KITE_REFRESH_STATUS=FAILED_VERIFICATION"
    assert alerts and "overlay remains disabled" in alerts[0]
    assert not hasattr(refresh, "mark_overlay_available")


def test_default_has_no_database_or_kv_token_write(monkeypatch):
    refresh = load_refresh()
    monkeypatch.setattr(refresh.psycopg2, "connect",
                        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("database write")))
    refresh.legacy_save_to_db("secret-token")
    source = SCRIPT.read_text(encoding="utf8")
    assert "KVNamespace" not in source
    assert "broker:kite:access-token" not in source


def test_legacy_database_write_requires_explicit_rollback_flag(monkeypatch):
    refresh = load_refresh()
    executed = []

    class Cursor:
        rowcount = 1
        def execute(self, query, params=None):
            executed.append((query, params))

    class Connection:
        def cursor(self): return Cursor()
        def commit(self): executed.append(("COMMIT", None))
        def close(self): pass

    monkeypatch.setattr(refresh.psycopg2, "connect", lambda *_a, **_k: Connection())
    refresh.legacy_save_to_db("secret-token")
    assert executed == []
    monkeypatch.setenv("ALLOW_LEGACY_KITE_DB_TOKEN_WRITE", "1")
    refresh.legacy_save_to_db("secret-token")
    assert any("platform_config" in query for query, _ in executed)
    assert any("kite_session" in query for query, _ in executed)


@pytest.mark.parametrize("entry", [
    "_scripts/refresh_kite_token.py",
    "pipeline/_scripts/refresh_kite_token.py",
])
def test_historical_entry_points_execute_canonical_logic(entry):
    env = os.environ.copy()
    env["KITE_REFRESH_TEST_MODE"] = "1"
    for name in ("EXECUTE_CLOUDFLARE_SECRET_ROTATION", "KITE_REFRESH_VALIDATE_ONLY",
                 "ALLOW_LEGACY_KITE_DB_TOKEN_WRITE"):
        env.pop(name, None)
    result = subprocess.run([sys.executable, entry], cwd=ROOT, env=env,
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert result.stdout.strip() == "KITE_REFRESH_STATUS=SKIPPED_NOT_ACTIVATED"
    assert "test-only-sensitive-access-token" not in result.stdout + result.stderr


def test_cron_classifies_every_structured_status():
    spec = importlib.util.spec_from_file_location("pipeline_cron_under_test", ROOT / "pipeline" / "cron.py")
    cron = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(cron)
    expected = {
        "SUCCESS_ROTATED": (0, "ok"),
        "SUCCESS_VALIDATED_ONLY": (0, "ok"),
        "SKIPPED_NOT_ACTIVATED": (0, "skipped"),
        "FAILED_LOGIN": (1, "failed"),
        "FAILED_ROTATION": (1, "failed"),
        "FAILED_VERIFICATION": (1, "failed"),
    }
    for status, (returncode, classification) in expected.items():
        assert cron.classify_kite_refresh(
            returncode, f"KITE_REFRESH_STATUS={status}\n") == (classification, status)
