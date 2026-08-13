import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

# Playwright is optional in CI; these tests exercise only pure manifest accounting.
playwright = ModuleType("playwright")
sync_api = ModuleType("playwright.sync_api")
sync_api.sync_playwright = lambda: None
sync_api.TimeoutError = type("TimeoutError", (Exception,), {})
sync_api.Error = type("Error", (Exception,), {})
playwright.sync_api = sync_api
sys.modules.setdefault("playwright", playwright)
sys.modules.setdefault("playwright.sync_api", sync_api)

SPEC = importlib.util.spec_from_file_location(
    "sebi_retry", Path(__file__).parents[1] / "download_sebi_rhps_playwright.py")
sebi = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sebi)


def args(maximum=None, override=False):
    return SimpleNamespace(max=maximum, retry_failed=override)


def setup(monkeypatch):
    monkeypatch.setattr(sebi, "save_manifest", lambda _manifest: None)
    monkeypatch.setattr(sebi, "polite_sleep", lambda _delay: None)
    monkeypatch.setattr(sebi, "log_failure", lambda *_args: None)


def summary(output):
    line = next(line for line in output.splitlines() if line.startswith("SEBI_DOWNLOAD_SUMMARY="))
    return json.loads(line.split("=", 1)[1])


def test_normal_run_retries_failure_and_success_clears_backlog(monkeypatch, capsys):
    setup(monkeypatch)
    manifest = {"filings": {"u": {"company":"A", "status":"failed_download", "attempts":1}}}
    monkeypatch.setattr(sebi, "download_one",
                        lambda _context, _url, rec: rec.update(status="ok", path="kept"))
    sebi.run_downloads(object(), manifest, args())
    result = summary(capsys.readouterr().out)
    assert result["this_run"] == {"succeeded":1, "failed":0, "retries":1}
    assert result["backlog"]["failed"] == 0 and result["status"] == "OK"


def test_exhausted_failure_is_owner_action_and_not_retried(monkeypatch, capsys):
    setup(monkeypatch); calls=[]
    manifest = {"filings": {"u": {"company":"A", "status":"failed_download",
                                      "attempts":sebi.MAX_RETRIES}}}
    monkeypatch.setattr(sebi, "download_one", lambda *_args: calls.append(1))
    sebi.run_downloads(object(), manifest, args())
    result = summary(capsys.readouterr().out)
    assert calls == [] and result["backlog"]["owner_action_exhausted"] == 1
    assert result["status"] == "PARTIAL"


def test_max_overflow_remains_retry_pending(monkeypatch, capsys):
    setup(monkeypatch)
    manifest = {"filings": {str(i): {"company":str(i), "status":"pending", "attempts":0}
                            for i in range(2)}}
    monkeypatch.setattr(sebi, "download_one",
                        lambda _context, _url, rec: rec.update(status="ok", path="kept"))
    sebi.run_downloads(object(), manifest, args(maximum=1))
    result = summary(capsys.readouterr().out)
    assert result["backlog"]["pending"] == 1 and result["status"] == "RETRY_PENDING"
