"""The shared Kite authentication helper must not depend on process cwd."""
import importlib
from pathlib import Path
import sys

import pytest

import cron
import kite_fetch


@pytest.mark.parametrize("working_directory", [
    kite_fetch.REPO_ROOT,
    kite_fetch.REPO_ROOT / "pipeline",
    None,
])
def test_shared_kite_helper_imports_from_every_working_directory(
        monkeypatch, tmp_path, working_directory):
    monkeypatch.chdir(working_directory or tmp_path)
    sys.modules.pop("kite_connect", None)

    helper = kite_fetch.load_shared_get_kite()
    module = importlib.import_module(helper.__module__)

    assert helper.__name__ == "get_kite"
    assert Path(module.__file__).resolve() == kite_fetch.REPO_ROOT / "_scripts/kite_connect.py"


def test_cron_keeps_explicit_pipeline_cwd_for_kite_fetch():
    source = Path(cron.__file__).read_text(encoding="utf-8")
    invocation = 'run("Daily candles/outcomes", KITE_FETCH_SCRIPT'
    start = source.index(invocation)
    assert "cwd=PIPELINE_DIR" in source[start:start + 250]
