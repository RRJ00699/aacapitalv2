"""Tests for _scripts/run_ipo_pipeline_lean.py — the nightly orchestrator.

In-process with subprocess.run FULLY stubbed (git self-update included — a
real run would hard-reset the working tree) and preflight stubbed for both
Kite branches. Asserts the ORDER contracts the pipeline exists to enforce.
"""
import sys, os, io, types, pathlib, subprocess as real_subprocess
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pytest
import run_ipo_pipeline_lean as P

pytestmark = pytest.mark.unit


class FakeProc:
    def __init__(self, rc=0, out="ok", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


@pytest.fixture
def orch(monkeypatch, tmp_path):
    """Stub everything that leaves the process; record step invocations."""
    ran = []
    def fake_run(cmd, **kw):
        if cmd[0] == "git":
            return FakeProc()                        # NEVER touch the real repo
        script = pathlib.Path(cmd[1]).name
        ran.append(script)
        return FakeProc(rc=fail.get(script, 0))
    fail = {}
    monkeypatch.setattr(P.subprocess, "run", fake_run)
    monkeypatch.setattr(P, "preflight", lambda: True)
    monkeypatch.setattr(P, "LOG", str(tmp_path / "p.log"))
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake-never-connects")
    monkeypatch.delenv("NEON_DATABASE_URL", raising=False)
    monkeypatch.delenv("HEALTHCHECK_URL", raising=False)
    return ran, fail, monkeypatch, tmp_path


def _main(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["run_ipo_pipeline_lean.py", *args])
    with pytest.raises(SystemExit) as e:
        P.main()
    return e.value.code


def test_daily_run_order_contracts(orch):
    ran, fail, mp, tmp = orch
    code = _main(mp)
    assert code == 0
    # the load-bearing ordering (SCHEMA gap fix): sync BEFORE rebuild BEFORE verdicts
    assert ran.index("sync_issue_details.py") < ran.index("build_ipo_consolidated_v2.py") \
           < ran.index("compute_verdicts.py")
    assert ran[0] == "schema_sync.py"                # DDL owner runs FIRST
    assert ran.index("check_data_contract.py") > ran.index("compute_flags.py")  # gate LAST block
    assert "purge_candles_after_lockin.py" not in ran     # weekly-only
    log = (tmp / "p.log").read_text(encoding="utf-8", errors="replace")
    assert "LEAN PIPELINE OK" in log

def test_kite_stale_skips_kite_steps_runs_rest(orch):
    ran, fail, mp, tmp = orch
    mp.setattr(P, "preflight", lambda: False)
    _main(mp)
    for kite_only in ("sync_inwindow_candles.py", "kite-sync-candles.py",
                      "fill_listing_open_from_candles.py"):
        assert kite_only not in ran
    assert "ipomatrix_ingest.py" in ran              # non-Kite work still runs (Chittorgarh steps removed 2026-07-23)
    assert "Kite token stale" in (tmp / "p.log").read_text(encoding="utf-8", errors="replace")

def test_weekly_flag_adds_purges(orch):
    ran, fail, mp, tmp = orch
    _main(mp, "--weekly")
    assert "purge_candles_after_lockin.py" in ran
    # Ledger #11 FIX: the dead purge_stale_data.py reference was removed —
    # no silent skip line pollutes the weekly log anymore.
    assert "purge_stale_data.py" not in ran
    assert "purge_stale_data" not in (tmp / "p.log").read_text(encoding="utf-8", errors="replace")

def test_consolidated_failure_exits_2_with_warning(orch):
    ran, fail, mp, tmp = orch
    fail["build_ipo_consolidated_v2.py"] = 1
    code = _main(mp)
    assert code == 2                                  # cron sees the red
    log = (tmp / "p.log").read_text(encoding="utf-8", errors="replace")
    assert "COMPLETED WITH WARNINGS" in log
    assert "rebuild consolidated exited 1" in log

def test_non_hard_step_failure_does_not_stop_run(orch):
    ran, fail, mp, tmp = orch
    fail["refresh_gmp.py"] = 1
    code = _main(mp)
    assert code == 0                                  # non-hard: run completes OK
    assert "compute_verdicts.py" in ran               # later steps still ran

def test_missing_script_skips_not_fails(orch, capsys):
    ran, fail, mp, tmp = orch
    assert P.step("ghost", ["does_not_exist_xyz.py"]) is True
    assert "not in repo — skipping" in (tmp / "p.log").read_text(encoding="utf-8", errors="replace")

def test_healthcheck_pinged_only_on_full_green(orch):
    ran, fail, mp, tmp = orch
    pings = []
    import urllib.request as _ur
    # the healthcheck pings via urlopen(Request(url)); record the URL, not the Request
    # object, so the contract is "which URL was pinged" regardless of arg wrapping.
    mp.setattr(_ur, "urlopen", lambda url, timeout=15: pings.append(getattr(url, "full_url", url)))
    mp.setenv("HEALTHCHECK_URL", "https://hc.example/ping")
    HC = "https://hc.example/ping"
    _main(mp)
    # The contract is "healthcheck fires IFF the pipeline is green" — not "exactly one
    # URL is ever pinged". Step 8 (KV cache-warm, 93d4783) also urlopen()s a warm URL,
    # so assert membership, not an exact single-element list.
    assert HC in pings, "healthcheck must fire on full green"
    # and NOT when a gate fails
    pings.clear(); fail["check_data_contract.py"] = 1
    _main(mp)
    assert HC not in pings, "healthcheck must NOT fire when a gate fails"


@pytest.mark.db
def test_stepboard_gets_greens_and_reds(orch, pg_uri):
    """Ledger #10 FIX: _log_step(..., True) now runs BEFORE the return —
    pipeline_steps receives every outcome, so the StepBoard shows greens."""
    import psycopg2
    ran, fail, mp, tmp = orch
    mp.setenv("DATABASE_URL", pg_uri)
    c = psycopg2.connect(pg_uri); c.autocommit = True
    c.cursor().execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
    fail["refresh_gmp.py"] = 1
    _main(mp)
    cur = c.cursor()
    cur.execute("SELECT COUNT(*) FILTER (WHERE ok), COUNT(*) FILTER (WHERE NOT ok) FROM pipeline_steps")
    greens, reds = cur.fetchone()
    assert reds == 1                                  # the seeded failure
    assert greens >= 20                               # every successful step logged
    cur.execute("SELECT ok FROM pipeline_steps WHERE step='refresh GMP'")
    assert cur.fetchone()[0] is False
    cur.execute("SELECT step FROM pipeline_failures")
    assert cur.fetchone()[0] == "refresh GMP"         # failure sink unchanged
    c.close()
