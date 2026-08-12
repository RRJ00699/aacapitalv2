"""Tests for check_data_contract MAIN (custom contract CSV vs embedded PG)
and schema_sync as a full subprocess run (per-statement isolation +
idempotency). Completes the health-gate coverage.
"""
import os, sys, csv, subprocess, pathlib
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration


def _run(script, uri, contract=None, *args):
    env = dict(os.environ, DATABASE_URL=uri)
    env.pop("NEON_DATABASE_URL", None)
    for k in [k for k in env if k.startswith(("COV_CORE", "COVERAGE"))]:
        env.pop(k)
    if contract:
        env["CONTRACT_CSV"] = str(contract)
    if os.environ.get("SUBPROC_COV"):
        env["COVERAGE_FILE"] = str(ROOT / ".coverage")
    diagnostic = ROOT / "tools" / "diagnostics" / script
    s = diagnostic if diagnostic.is_file() else ROOT / "_scripts" / script
    cmd = ([sys.executable, "-m", "coverage", "run", "-p",
            f"--rcfile={ROOT}/.coveragerc", str(s)]
           if os.environ.get("SUBPROC_COV") else [sys.executable, str(s)])
    env["PYTHONIOENCODING"] = "utf-8"        # child writes UTF-8 banners (✅, box-drawing)
    return subprocess.run([*cmd, *args], capture_output=True, text=True,
                          encoding="utf-8", env=env, timeout=120, cwd=ROOT)


def _contract(tmp_path, rows):
    p = tmp_path / "contract.csv"
    cols = ["dimension", "field", "source_table", "source_column",
            "populator_script", "consumed_by", "coverage_now", "status", "action_to_fix"]
    with open(p, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader()
        for r in rows:
            w.writerow({**{c: "" for c in cols}, **r})
    return p


@pytest.fixture
def cdc_db(pg_uri):
    import psycopg2
    c = psycopg2.connect(pg_uri); c.autocommit = True; cur = c.cursor()
    cur.execute("""DROP SCHEMA public CASCADE; CREATE SCHEMA public;
        CREATE TABLE ipo_intelligence (company_name TEXT, nse_symbol TEXT,
                                       tier1_count INT)""")
    cur.execute("""INSERT INTO ipo_intelligence VALUES
        ('A Ltd','A1',5), ('B Ltd','B1',0), ('C Ltd',NULL,NULL)""")
    yield pg_uri, c
    c.close()


# ---------------- check_data_contract main ----------------

def test_cdc_pass_when_live_at_baseline(cdc_db, tmp_path):
    uri, c = cdc_db
    ct = _contract(tmp_path, [
        {"field": "nse_symbol", "source_table": "ipo_intelligence",
         "source_column": "nse_symbol", "coverage_now": "2/3", "status": "LIVE"}])
    r = _run("check_data_contract.py", uri, ct)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "✅ PASS" in r.stdout and "0 regression" in r.stdout

def test_cdc_regression_exits_1(cdc_db, tmp_path):
    uri, c = cdc_db
    ct = _contract(tmp_path, [
        {"field": "nse_symbol", "source_table": "ipo_intelligence",
         "source_column": "nse_symbol", "coverage_now": "100/100", "status": "LIVE"}])
    r = _run("check_data_contract.py", uri, ct)
    assert r.returncode == 1
    assert "REGRESSED" in r.stdout and "FAIL" in r.stdout

def test_cdc_schema_break_on_vanished_column(cdc_db, tmp_path):
    """The prune-dead-columns failure class: contract names a col that's gone."""
    uri, c = cdc_db
    ct = _contract(tmp_path, [
        {"field": "ghost", "source_table": "ipo_intelligence",
         "source_column": "vanished_col", "coverage_now": "10", "status": "LIVE"}])
    r = _run("check_data_contract.py", uri, ct)
    assert r.returncode == 1 and "SCHEMA BREAK" in r.stdout

def test_cdc_watch_and_no_source_rows_never_fail(cdc_db, tmp_path):
    uri, c = cdc_db
    ct = _contract(tmp_path, [
        {"field": "broken_field", "source_table": "ipo_intelligence",
         "source_column": "nse_symbol", "coverage_now": "999", "status": "BROKEN"},
        {"field": "future", "source_table": "(planned)", "source_column": "(tbd)",
         "status": "FORWARD-ONLY"}])
    r = _run("check_data_contract.py", uri, ct)
    assert r.returncode == 0
    assert "watch [BROKEN]" in r.stdout and "(no source yet)" in r.stdout

def test_cdc_tier1_uses_gt_zero_predicate(cdc_db, tmp_path):
    """tier1 fields count >0, not NOT-NULL: 5,0,NULL -> current 1."""
    uri, c = cdc_db
    ct = _contract(tmp_path, [
        {"field": "tier1_count", "source_table": "ipo_intelligence",
         "source_column": "tier1_count", "coverage_now": "1", "status": "LIVE"}])
    r = _run("check_data_contract.py", uri, ct)
    assert r.returncode == 0
    assert f"{'1':>6}{'1':>7}" in r.stdout               # base 1, now 1

def test_cdc_twins_fail_even_when_fields_pass(cdc_db, tmp_path):
    uri, c = cdc_db
    c.cursor().execute("""INSERT INTO ipo_intelligence VALUES
        ('A Limited','A2',1)""")                         # canonical twin of 'A Ltd'
    ct = _contract(tmp_path, [
        {"field": "nse_symbol", "source_table": "ipo_intelligence",
         "source_column": "nse_symbol", "coverage_now": "1", "status": "LIVE"}])
    r = _run("check_data_contract.py", uri, ct)
    assert r.returncode == 1
    assert "twin census" in r.stdout

def test_cdc_update_baselines_rewrites_csv(cdc_db, tmp_path):
    uri, c = cdc_db
    ct = _contract(tmp_path, [
        {"field": "nse_symbol", "source_table": "ipo_intelligence",
         "source_column": "nse_symbol", "coverage_now": "1/3", "status": "LIVE"}])
    r = _run("check_data_contract.py", uri, ct, "--update-baselines")
    assert r.returncode == 0 and "baselines rewritten" in r.stdout
    rows = list(csv.DictReader(open(ct)))
    assert rows[0]["coverage_now"] == "2"                # rewritten from live count


# ---------------- schema_sync full run ----------------

APP_TABLES = """
    CREATE TABLE ipo_intelligence (company_name TEXT);
    CREATE TABLE ipo_consolidated (company_name TEXT);
    CREATE TABLE ipo_verdicts (company_name TEXT);
    CREATE TABLE ipo_tick_feed (symbol TEXT, recorded_at TIMESTAMPTZ);
    CREATE TABLE ipo_level_analysis (symbol TEXT, trade_date DATE);
    CREATE TABLE ipo_research_notes (company TEXT, source TEXT);
    CREATE TABLE ipo_rhp_intel (company_name TEXT);
    CREATE TABLE access_requests (email TEXT PRIMARY KEY);
"""

@pytest.fixture
def sync_pg(pg_uri):
    """Prod-shaped: the app tables exist (created by their writers); sync
    then applies guardrail DDL on top -> full run must be green."""
    import psycopg2
    c = psycopg2.connect(pg_uri); c.autocommit = True
    c.cursor().execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;" + APP_TABLES)
    yield pg_uri, c
    c.close()

def test_schema_sync_bootstraps_guardrail_objects(sync_pg):
    uri, c = sync_pg
    r = _run("schema_sync.py", uri)
    assert r.returncode == 0, r.stdout + r.stderr
    cur = c.cursor()
    for t in ("pipeline_failures", "pipeline_steps", "data_source_registry",
              "data_lineage", "ingestion_audit", "data_freshness", "job_runs"):
        cur.execute("SELECT to_regclass(%s)", (t,))
        assert cur.fetchone()[0], f"{t} not created"
    cur.execute("SELECT source FROM data_source_registry WHERE domain='vix'")
    assert cur.fetchone()[0] == "kite"                   # guardrail C seeded


def test_schema_sync_owns_access_request_note(sync_pg):
    _uri, c = sync_pg
    assert _run("schema_sync.py", _uri).returncode == 0
    cur = c.cursor()
    cur.execute("""SELECT 1 FROM information_schema.columns
                   WHERE table_name='access_requests' AND column_name='note'""")
    assert cur.fetchone() == (1,)

def test_schema_sync_per_statement_isolation_on_fresh_db(pg_uri):
    """FRESH empty db: statements targeting absent app tables fail (exit 1,
    loudly counted) — but everything else still lands. That partial-apply
    IS the per-statement isolation guarantee."""
    import psycopg2
    c = psycopg2.connect(pg_uri); c.autocommit = True
    c.cursor().execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
    r = _run("schema_sync.py", pg_uri)
    assert r.returncode == 1                             # failures are LOUD
    assert "FAILED (isolated" in r.stdout
    cur = c.cursor()
    cur.execute("SELECT to_regclass('data_lineage')")
    assert cur.fetchone()[0]                             # later statement landed anyway
    c.close()

def test_schema_sync_idempotent_second_run(sync_pg):
    uri, c = sync_pg
    assert _run("schema_sync.py", uri).returncode == 0
    r2 = _run("schema_sync.py", uri)
    assert r2.returncode == 0                            # IF NOT EXISTS everywhere

def test_schema_sync_dedups_then_uniques(sync_pg):
    """GUARDRAIL A end-to-end: pre-seed canonical dup companies -> sync
    deletes the twin and the unique index then holds."""
    import psycopg2
    uri, c = sync_pg
    cur = c.cursor()
    cur.execute("""INSERT INTO ipo_intelligence VALUES
        ('Antony Waste Ltd'), ('Antony Waste Limited')""")
    r = _run("schema_sync.py", uri)
    assert r.returncode == 0
    cur.execute("SELECT COUNT(*) FROM ipo_intelligence")
    assert cur.fetchone()[0] == 1                        # twin self-healed away
    with pytest.raises(psycopg2.errors.UniqueViolation):
        cur.execute("INSERT INTO ipo_intelligence VALUES ('ANTONY WASTE PVT LTD.')")
    c.close()
