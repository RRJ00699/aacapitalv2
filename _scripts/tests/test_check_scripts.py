"""Pytest conversion of the three health-gate check scripts (roadmap Phase 1.4):
  check_value_sanity.py  — run as subprocess vs embedded PG (integration)
  check_dupes.py         — run as subprocess vs embedded PG (integration)
  check_data_contract.py — baseline_num unit + check_twin_census vs embedded PG

All hermetic: embedded Postgres only, never production. The scripts stay the
CLI tools; these tests make their behavior part of the CI gate.
"""
import os, sys, subprocess, pathlib, importlib.util
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "_scripts"
sys.path.insert(0, str(SCRIPTS))


# ---------------- helpers ----------------

def _run(script, uri, *args):
    env = dict(os.environ, DATABASE_URL=uri)
    env.pop("NEON_DATABASE_URL", None)          # never let a real DB leak in
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args],
                          capture_output=True, text=True, env=env, timeout=60)

def _load_cdc(uri):
    """Import check_data_contract with its module-level env/CSV checks satisfied."""
    os.environ["DATABASE_URL"] = uri
    os.environ["CONTRACT_CSV"] = str(SCRIPTS / "ipo_data_contract.csv")
    argv, sys.argv = sys.argv, ["check_data_contract.py"]
    try:
        spec = importlib.util.spec_from_file_location("cdc", SCRIPTS / "check_data_contract.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        sys.argv = argv


@pytest.fixture
def sanity_db(pg_uri):
    """Schema shaped for the value-sanity CHECKS + dupes queries."""
    import psycopg2
    c = psycopg2.connect(pg_uri); c.autocommit = True; cur = c.cursor()
    cur.execute("""DROP SCHEMA public CASCADE; CREATE SCHEMA public;
        CREATE TABLE ipo_intelligence (
            company_name TEXT, nse_symbol TEXT, issue_price NUMERIC,
            listing_open NUMERIC, listing_gap_pct NUMERIC, peer_median_pe NUMERIC,
            ipo_pe NUMERIC, roe NUMERIC, listing_date DATE,
            open_date DATE, close_date DATE, total_subscription_x NUMERIC);
        CREATE TABLE ipo_consolidated (
            company_name TEXT, nse_symbol TEXT, symbol_final TEXT,
            listing_date DATE, issue_size_cr NUMERIC, ipo_score INT);
        CREATE TABLE ipo_verdicts (
            company_name TEXT, verdict TEXT, score INT, confidence TEXT);""")
    yield pg_uri, c
    c.close()


GOOD = """INSERT INTO ipo_intelligence
    (company_name, nse_symbol, issue_price, listing_open, listing_gap_pct,
     peer_median_pe, ipo_pe, roe, listing_date, open_date, close_date, total_subscription_x)
    VALUES ('Clean Ltd','CLEAN',100,110,10, 25,30,15, CURRENT_DATE, CURRENT_DATE-7, CURRENT_DATE-5, 12)"""


# ---------------- check_value_sanity.py ----------------

@pytest.mark.integration
def test_value_sanity_clean_passes(sanity_db):
    uri, c = sanity_db
    c.cursor().execute(GOOD)
    r = _run("check_value_sanity.py", uri)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PASS" in r.stdout

@pytest.mark.integration
def test_value_sanity_nulls_are_not_violations(sanity_db):
    uri, c = sanity_db
    c.cursor().execute("INSERT INTO ipo_intelligence (company_name) VALUES ('All Nulls Ltd')")
    r = _run("check_value_sanity.py", uri)
    assert r.returncode == 0

@pytest.mark.integration
@pytest.mark.parametrize("col,val,checkname", [
    ("issue_price", "-5", "issue_price > 0"),
    ("listing_gap_pct", "600", "listing_gap_pct in [-100,500]"),
    ("peer_median_pe", "0", "peer_median_pe in (0,500]"),
    ("total_subscription_x", "-1", "total_subscription_x >= 0"),
])
def test_value_sanity_hard_violations_exit_1(sanity_db, col, val, checkname):
    uri, c = sanity_db
    c.cursor().execute(f"INSERT INTO ipo_intelligence (nse_symbol, {col}) VALUES ('BAD', {val})")
    r = _run("check_value_sanity.py", uri)
    assert r.returncode == 1
    assert "FAIL" in r.stdout and "BAD" in r.stdout   # offender symbol shown

@pytest.mark.integration
def test_value_sanity_open_after_close_is_hard(sanity_db):
    """The class-D date bug: open_date > close_date must fail the gate."""
    uri, c = sanity_db
    c.cursor().execute("""INSERT INTO ipo_intelligence (nse_symbol, open_date, close_date)
        VALUES ('DATES', CURRENT_DATE, CURRENT_DATE - 3)""")
    r = _run("check_value_sanity.py", uri)
    assert r.returncode == 1

@pytest.mark.integration
def test_value_sanity_warn_only_passes_unless_flag(sanity_db):
    uri, c = sanity_db
    c.cursor().execute("INSERT INTO ipo_intelligence (nse_symbol, roe) VALUES ('W', 400)")
    assert _run("check_value_sanity.py", uri).returncode == 0
    assert _run("check_value_sanity.py", uri, "--fail-on-warn").returncode == 1

@pytest.mark.integration
def test_value_sanity_missing_columns_skip_not_crash(sanity_db):
    uri, c = sanity_db
    cur = c.cursor()
    cur.execute("CREATE TABLE slim (nse_symbol TEXT, issue_price NUMERIC)")
    cur.execute("INSERT INTO slim VALUES ('OK', 100)")
    r = _run("check_value_sanity.py", uri, "--table", "slim")
    assert r.returncode == 0 and "skip" in r.stdout

@pytest.mark.integration
def test_value_sanity_unknown_table_exits_nonzero(sanity_db):
    uri, _ = sanity_db
    assert _run("check_value_sanity.py", uri, "--table", "nope").returncode != 0


# ---------------- check_dupes.py ----------------

@pytest.mark.integration
def test_check_dupes_finds_variant_group(sanity_db):
    """The Kusumgar incident shape: 'Ltd.' vs 'Ltd. O' must group as one dupe."""
    uri, c = sanity_db
    cur = c.cursor()
    cur.execute("""INSERT INTO ipo_consolidated (company_name) VALUES
        ('Kusumgar Ltd.'), ('Kusumgar Ltd. O'), ('Unique Co Ltd')""")
    r = _run("check_dupes.py", uri)
    assert r.returncode == 0
    assert "found 1 duplicate groups" in r.stdout
    assert "Kusumgar Ltd. || Kusumgar Ltd. O" in r.stdout

@pytest.mark.integration
def test_check_dupes_clean_db_reports_zero(sanity_db):
    uri, c = sanity_db
    c.cursor().execute("INSERT INTO ipo_consolidated (company_name) VALUES ('Solo Ltd')")
    r = _run("check_dupes.py", uri)
    assert "found 0 duplicate groups" in r.stdout


# ---------------- check_data_contract.py (importable pieces) ----------------

@pytest.mark.unit
def test_baseline_num_parsing(pg_uri):
    m = _load_cdc(pg_uri)
    assert m.baseline_num("310/432") == 310
    assert m.baseline_num("~25 days") == 25
    assert m.baseline_num(" 7") == 7
    assert m.baseline_num("n/a") is None
    assert m.baseline_num(None) is None

@pytest.mark.db
def test_twin_census_catches_canonical_twins(sanity_db):
    """Guardrail B backstop: 'Antony Waste Ltd' vs 'Antony Waste Limited'
    canonicalize identically → counted as a twin."""
    uri, c = sanity_db
    cur = c.cursor()
    cur.execute("""INSERT INTO ipo_intelligence (company_name) VALUES
        ('Antony Waste Ltd'), ('Antony Waste Limited'), ('Different Co Ltd')""")
    m = _load_cdc(uri)
    assert m.check_twin_census(cur) == 1

@pytest.mark.db
def test_twin_census_clean_returns_zero(sanity_db):
    uri, c = sanity_db
    cur = c.cursor()
    cur.execute("INSERT INTO ipo_intelligence (company_name) VALUES ('Alpha Ltd'), ('Beta Ltd')")
    m = _load_cdc(uri)
    assert m.check_twin_census(cur) == 0
