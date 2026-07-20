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
    """Incident 2026-07-21: deploy raced the VM schema run and the screen
    degraded on relation "ipo_insights" does not exist. The route self-heals
    with inline DDL — which must stay BYTE-EQUIVALENT (normalized) to
    schema_sync's, so the single-DDL-owner rule holds."""
    import os, re
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    repo = os.path.dirname(root)

    def norm(sql):
        return re.sub(r"\s+", " ", sql).strip().rstrip(";").lower()

    route = open(os.path.join(repo, "app", "api", "ipo-command", "route.ts"), encoding="utf-8").read()
    m = re.search(r"await sql`(CREATE TABLE IF NOT EXISTS ipo_insights .*?)`", route, re.S)
    assert m, "route must self-heal ipo_insights before querying it"
    sync = open(os.path.join(root, "schema_sync.py"), encoding="utf-8").read()
    m2 = re.search(r'"""(CREATE TABLE IF NOT EXISTS ipo_insights .*?)"""', sync, re.S)
    assert m2, "schema_sync must own the authoritative DDL"
    assert norm(m.group(1)) == norm(m2.group(1)), \
        "route inline DDL diverged from schema_sync — update BOTH or the self-heal creates the wrong shape"


def test_cards_query_survives_missing_insights_table(pg_uri):
    """EXECUTED deploy-order proof: fresh DB WITHOUT ipo_insights; run the
    route's self-heal DDL, then the real cards query — no degraded mode."""
    import os, re, sys
    import psycopg2
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    repo = os.path.dirname(root)
    sys.path.insert(0, root)
    tests = os.path.join(root, "tests")
    sys.path.insert(0, tests)
    from contract_schema import CONTRACT_DDL
    route = open(os.path.join(repo, "app", "api", "ipo-command", "route.ts"), encoding="utf-8").read()
    heal = re.search(r"await sql`(CREATE TABLE IF NOT EXISTS ipo_insights .*?)`", route, re.S).group(1)
    cards_sql = re.search(r"const cards = await sql`\n(.*?)`;", route, re.S).group(1)
    cards_sql = re.sub(r"\$\{[^}]*\}", "NULL", cards_sql).replace("\\\\", "\\")
    c = psycopg2.connect(pg_uri); c.autocommit = True; cur = c.cursor()
    cur.execute(CONTRACT_DDL)
    cur.execute("DROP TABLE IF EXISTS ipo_insights")          # the incident state
    cur.execute(heal)                                          # route self-heal
    cur.execute(cards_sql)                                     # the real query
    cur.fetchall()                                             # no NeonDbError-equivalent
    c.close()


def test_expected_steps_mirror_the_lean_pipeline_exactly():
    """The Pipeline-health board's EXPECTED list must equal the lean
    pipeline's actual step() names — that mirror is what makes a silently
    missing step (the peer-PE ghost) VISIBLE. Divergence fails here."""
    import os, re
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    repo = os.path.dirname(root)
    lean = open(os.path.join(root, "run_ipo_pipeline_lean.py"), encoding="utf-8").read()
    lean_steps = re.findall(r'step\("([^"]+)"', lean)
    route = open(os.path.join(repo, "app", "api", "admin", "pipeline-steps", "route.ts"), encoding="utf-8").read()
    ui_steps = re.findall(r'\{ step: "([^"]+)"', route)
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
