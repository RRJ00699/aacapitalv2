"""Integration tests for compatibility/consolidated/build_ipo_consolidated_v2.py main() — the
nightly builder of the table the API reads. Subprocess vs embedded PG.

The builder SELF-HEALS: missing source columns become NULL (loudly), missing
optional tables skip their JOIN — so it must run on a minimal schema. That
self-heal is the guard born from the 2026-07-08 'rebuild exited 1' incident;
these tests make it CI-enforced.
"""
import os, sys, subprocess, pathlib
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration


def _run(uri):
    env = dict(os.environ, DATABASE_URL=uri)
    env.pop("NEON_DATABASE_URL", None)
    for k in [k for k in env if k.startswith(("COV_CORE", "COVERAGE"))]:
        env.pop(k)
    script = ROOT / "compatibility" / "consolidated" / "build_ipo_consolidated_v2.py"
    cmd = ([sys.executable, "-m", "coverage", "run", "-p",
            f"--rcfile={ROOT}/.coveragerc", str(script)]
           if os.environ.get("SUBPROC_COV") else [sys.executable, str(script)])
    env["PYTHONIOENCODING"] = "utf-8"        # child writes UTF-8 (banners / non-ASCII)
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          env=env, timeout=120, cwd=ROOT)


@pytest.fixture
def build_db(pg_uri):
    """Minimal ipo_intelligence only — issue_details/subscription ABSENT on
    purpose, to exercise the optional-table skip path."""
    import psycopg2
    c = psycopg2.connect(pg_uri); c.autocommit = True; cur = c.cursor()
    cur.execute("""DROP SCHEMA public CASCADE; CREATE SCHEMA public;
        CREATE TABLE ipo_intelligence (
            company_name TEXT, nse_symbol TEXT, symbol TEXT,
            issue_price NUMERIC, listing_open NUMERIC, listing_date DATE,
            ipo_pe NUMERIC, peer_median_pe NUMERIC, pat_cr NUMERIC);""")
    cur.execute("""INSERT INTO ipo_intelligence VALUES
        ('Mid Gap Ltd',  'MIDGAP', NULL,     100, 110, '2026-06-01', 30, 20, 50),
        ('High Gap Ltd', NULL,     'highsym',100, 130, '2026-06-02', NULL, NULL, -5),
        ('Low Gap Ltd',  'LOWGAP', NULL,     100, 102, '2026-06-03', 10, 20, 0),
        ('No Open Ltd',  'NOOPEN', NULL,     100, NULL,'2026-06-04', NULL, NULL, NULL)""")
    yield pg_uri, c
    c.close()


def _consol(c):
    cur = c.cursor()
    cur.execute("""SELECT company_name, symbol_final, gap_bucket, is_profitable,
                          valuation_premium, tp1_exit_note
                   FROM ipo_consolidated ORDER BY company_name""")
    return {r[0]: r[1:] for r in cur.fetchall()}


def test_builds_on_minimal_schema_with_self_heal(build_db):
    """Missing source cols -> NULL, loudly; missing optional tables -> skipped."""
    uri, c = build_db
    r = _run(uri)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "not present" in r.stdout                       # optional tables skipped
    assert "swapped" in r.stdout or "NULL" in r.stdout or "missing" in r.stdout.lower()
    assert "ipo_consolidated v2 built: 4 rows" in r.stdout

def test_symbol_final_resolution(build_db):
    """nse_symbol preferred; falls back to symbol; both uppercased."""
    uri, c = build_db
    _run(uri)
    rows = _consol(c)
    assert rows["Mid Gap Ltd"][0] == "MIDGAP"
    assert rows["High Gap Ltd"][0] == "HIGHSYM"            # fallback, uppercased

def test_gap_bucket_thresholds(build_db):
    """The locked 4/15 band (aligned 2026-07-08): <4 LOW, 4-15 MID, >15 HIGH."""
    uri, c = build_db
    _run(uri)
    rows = _consol(c)
    assert rows["Low Gap Ltd"][1] == "LOW"                 # +2%
    assert rows["Mid Gap Ltd"][1] == "MID"                 # +10%
    assert rows["High Gap Ltd"][1] == "HIGH"               # +30%
    assert rows["No Open Ltd"][1] is None                  # no listing_open -> NULL

def test_is_profitable_and_valuation_premium(build_db):
    uri, c = build_db
    _run(uri)
    rows = _consol(c)
    assert rows["Mid Gap Ltd"][2] is True                  # pat 50
    assert rows["High Gap Ltd"][2] is False                # pat -5
    assert rows["Low Gap Ltd"][2] is False                 # pat 0 -> not > 0
    assert float(rows["Mid Gap Ltd"][3]) == 50.0           # (30-20)/20*100
    assert rows["High Gap Ltd"][3] is None                 # no PEs -> no premium

def test_tp1_note_only_on_mid(build_db):
    uri, c = build_db
    _run(uri)
    rows = _consol(c)
    assert rows["Mid Gap Ltd"][4] and "MID-gap" in rows["Mid Gap Ltd"][4]
    assert rows["High Gap Ltd"][4] is None

def test_idempotent_rebuild_no_drift(build_db):
    """DROP+CREATE each run: same input twice -> identical table, no dup rows."""
    uri, c = build_db
    _run(uri); first = _consol(c)
    r2 = _run(uri); second = _consol(c)
    assert r2.returncode == 0
    assert first == second and len(second) == 4

def test_regime_join_when_market_regimes_present(build_db):
    """Runtime column discovery: regime + vix attach on listing_date, vix
    fill-empty-only."""
    uri, c = build_db
    cur = c.cursor()
    cur.execute("""CREATE TABLE market_regimes
        (evaluation_date DATE, active_regime TEXT, india_vix NUMERIC)""")
    cur.execute("""INSERT INTO market_regimes VALUES ('2026-06-01','BULL',14.2)""")
    r = _run(uri)
    assert r.returncode == 0
    cur.execute("""SELECT regime_at_listing, india_vix FROM ipo_consolidated
                   WHERE company_name='Mid Gap Ltd'""")
    reg, vix = cur.fetchone()
    assert reg == "BULL" and float(vix) == 14.2
    cur.execute("""SELECT regime_at_listing FROM ipo_consolidated
                   WHERE company_name='High Gap Ltd'""")
    assert cur.fetchone()[0] is None                       # no regime row that day

def test_missing_db_url_exits_loud():
    env = {k: v for k, v in os.environ.items()
           if k not in ("DATABASE_URL", "NEON_DATABASE_URL")}
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run([sys.executable, str(ROOT / "compatibility" / "consolidated" / "build_ipo_consolidated_v2.py")],
                       capture_output=True, text=True, encoding="utf-8", env=env, timeout=60)
    assert r.returncode != 0 and "DATABASE_URL" in (r.stdout + r.stderr)
