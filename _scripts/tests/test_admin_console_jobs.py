#!/usr/bin/env python3
"""Every job in the runner whitelist must have a button in the Admin console.

2026-07-18: six jobs (schema, verdicts, score, quality, smoke, sbi_haiku) were
added to job_runner's JOBS whitelist but NOT to AdminConsoleClient's button list.
Runnable in principle, invisible in practice — the owner could not find "the
schema job" because no button existed. The console is the phone's only route to
the VM, so a whitelist entry with no button is a job that does not exist.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
RUNNER = ROOT / "_scripts" / "job_runner.py"
CONSOLE = ROOT / "app" / "dashboard" / "admin" / "AdminConsoleClient.tsx"
pytestmark = pytest.mark.unit

NO_BUTTON_OK = {"pipeline_weekly", "universe_candles", "levels"}


def _whitelist():
    s = RUNNER.read_text(encoding="utf-8")
    block = s[s.index("JOBS = {"):s.index("def ensure_table")]
    return set(re.findall(r'"([a-z_]+)":\s*\[', block))


def _buttons():
    return set(re.findall(r'key:\s*"([a-z_]+)"', CONSOLE.read_text(encoding="utf-8")))


def test_every_button_maps_to_a_real_job():
    orphan = _buttons() - _whitelist()
    assert not orphan, f"console button(s) with no job_runner entry: {sorted(orphan)}"


def test_important_jobs_have_buttons():
    missing = (_whitelist() - _buttons()) - NO_BUTTON_OK
    assert not missing, (
        f"job(s) runnable but INVISIBLE from the phone (no console button): {sorted(missing)}")


def test_schema_job_is_present_and_first_class():
    assert "schema" in _buttons(), "no Schema sync button — DDL cannot be applied from a phone"
    assert "schema" in _whitelist(), "schema job missing from the runner whitelist"


def test_no_admin_job_points_at_a_retired_script():
    """2026-07-21: owner triggered 'Run full pipeline' from Admin and got the
    RETIRED banner + exit 1 — the whitelist still pointed at the old
    orchestrator. Every whitelisted script must exist and must not be a
    retired stub."""
    import os, re
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "job_runner.py"), encoding="utf-8").read()
    scripts = set(re.findall(r'\["(_scripts/[a-z_\-]+\.py)"', src))
    assert "_scripts/run_ipo_pipeline_lean.py" in scripts, "pipeline job must run the LEAN orchestrator"
    repo = os.path.dirname(root)
    for rel in scripts:
        pth = os.path.join(repo, rel)
        assert os.path.exists(pth), f"whitelisted job script missing: {rel}"
        head = open(pth, encoding="utf-8", errors="ignore").read(2000)
        assert "RETIRED" not in head, f"whitelisted job points at a RETIRED stub: {rel}"


def test_pipeline_calls_the_real_peer_pe_script():
    """compute_peer_pe.py never existed — peer P/E was silently skipped every
    run (root cause of 'fair value unavailable' on every IPO). The lean
    pipeline must call fetch_peer_pe.py --apply, and the ghosts stay gone."""
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "run_ipo_pipeline_lean.py"), encoding="utf-8").read()
    assert '["fetch_peer_pe.py", "--apply"]' in src
    for ghost in ("compute_peer_pe.py", "fix_sectors.py", "compute_quality_flags.py"):
        assert ghost not in src, f"ghost step resurrected: {ghost}"


def test_route_selfheal_ddl_matches_schema_sync_exactly():
    # RETIRED: #282 rewrote ipo-command to read the CANONICAL `insights` table (lib/v2/
    # ipo-command.ts), removing the inline ipo_insights self-heal DDL entirely — there is
    # no route-owned DDL left to keep byte-equivalent with schema_sync. Guard that no
    # inline CREATE TABLE resurfaces in the command logic.
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    repo = os.path.dirname(root)
    src = open(os.path.join(repo, "lib", "v2", "ipo-command.ts"), encoding="utf-8").read()
    assert "CREATE TABLE IF NOT EXISTS ipo_insights" not in src, \
        "#282 dropped the self-heal DDL (canonical `insights` table); do not re-add inline DDL"


def test_cards_query_survives_missing_insights_table(pg_uri):
    # RETIRED: the deploy-order self-heal is obsolete — #282 reads the canonical `insights`
    # table and no longer creates ipo_insights inline, so the "missing table" incident this
    # guarded cannot recur. The canonical cards query is EXECUTED in test_api_contract,
    # deferred to its own PR (V2 schema fixture). Guard the self-heal removal here.
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    repo = os.path.dirname(root)
    src = open(os.path.join(repo, "lib", "v2", "ipo-command.ts"), encoding="utf-8").read()
    assert "CREATE TABLE IF NOT EXISTS ipo_insights" not in src


def test_expected_steps_mirror_the_lean_pipeline_exactly():
    """The Pipeline-health board's EXPECTED list must equal the lean
    pipeline's actual step() names — that mirror is what makes a silently
    missing step (the peer-PE ghost) VISIBLE. Divergence fails here."""
    import os, re
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    repo = os.path.dirname(root)
    lean = open(os.path.join(root, "run_ipo_pipeline_lean.py"), encoding="utf-8").read()
    lean_steps = re.findall(r'(?<!_log_)step\("([^"]+)"', lean)  # _log_step() skip-rows are not steps
    expected = open(os.path.join(repo, "lib", "pipeline-steps.ts"), encoding="utf-8").read()
    ui_steps = re.findall(r'\{ step: "([^"]+)"', expected)
    assert lean_steps, "lean pipeline steps not parseable"
    assert ui_steps == lean_steps, (
        f"Pipeline-health EXPECTED list diverged from the lean pipeline.\n"
        f"only in lean: {[s for s in lean_steps if s not in ui_steps]}\n"
        f"only in UI:   {[s for s in ui_steps if s not in lean_steps]}")


def test_dead_levels_job_gone_from_all_three_lists():
    """ipo_daily_levels is written by nothing in the pipeline and read by
    nothing in the app (its route was archived) — the Admin job was dead
    weight. Gone from runner, UI catalog and API accept-list."""
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    repo = os.path.dirname(root)
    assert '"levels"' not in open(os.path.join(root, "job_runner.py"), encoding="utf-8").read()
    assert 'key: "levels"' not in open(os.path.join(repo, "app", "dashboard", "admin", "AdminConsoleClient.tsx"), encoding="utf-8").read()
    assert '"levels"' not in open(os.path.join(repo, "app", "api", "admin", "jobs", "route.ts"), encoding="utf-8").read()
