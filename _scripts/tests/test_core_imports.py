"""Core import-surface test.

Two jobs:
1. Every core module must IMPORT without side effects (no DB connect, no
   stdout re-wrap, no sys.exit at import) — the rhp_sonnet stdout-wrap and
   check_dupes connect-at-import classes fail here for any new module.
2. Importing registers every core file with coverage, so the core
   denominator in .coveragerc is honest — an untested module shows 0%,
   not invisible.

Documented exceptions (import-unsafe BY DESIGN, measured via subprocess):
  - check_dupes.py        connects to DB at module level
  - rhp_sonnet.py         re-wraps sys.stdout at import (bug ledger #8)
  - check_data_contract   sys.exits at import without env (loaded via helper)
"""
import sys, os, pathlib, importlib.util
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.unit

CORE_IMPORT_SAFE = [
    "ipo_score", "compute_verdicts", "compute_flags", "parse_sbi_notes",
    "check_value_sanity", "sync_issue_details", "schema_sync",
    "build_ipo_consolidated_v2", "fetch_peer_pe", "compute_quality_score",
    "run_ipo_pipeline_lean",
]

@pytest.mark.parametrize("mod", CORE_IMPORT_SAFE)
def test_core_module_imports_cleanly(mod, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://import-test-never-connect")
    monkeypatch.setattr(sys, "argv", [mod])
    out, err = sys.stdout, sys.stderr
    spec = importlib.util.spec_from_file_location(f"coreimp_{mod}", ROOT / "_scripts" / f"{mod}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)                       # raises on import-time side crash
    assert sys.stdout is out and sys.stderr is err, \
        f"{mod} re-wraps stdio at import (rhp_sonnet bug class — move it into main())"
    assert callable(getattr(m, "main", None)), f"{mod} has no main() entrypoint"
