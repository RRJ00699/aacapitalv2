"""Integration tests for the pipeline mains — ipo_score, compute_verdicts,
compute_flags — run as subprocesses vs embedded PG. Covers the DB
orchestration the unit tests can't: introspection-based column healing,
ON CONFLICT upserts, the locked BAND_STATS write, the confidence
string->numeric boundary (the 2026-07-17 'invalid input syntax: low' crash),
and dry-run vs --apply.
"""
import os, sys, subprocess, pathlib
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration


def _run(script, uri, *args):
    env = dict(os.environ, DATABASE_URL=uri)
    env.pop("NEON_DATABASE_URL", None)
    for k in [k for k in env if k.startswith(("COV_CORE", "COVERAGE"))]:
        env.pop(k)
    s = ROOT / "_scripts" / script
    cmd = ([sys.executable, "-m", "coverage", "run", "-p",
            f"--rcfile={ROOT}/.coveragerc", str(s)]
           if os.environ.get("SUBPROC_COV") else [sys.executable, str(s)])
    return subprocess.run([*cmd, *args], capture_output=True, text=True,
                          env=env, timeout=120, cwd=ROOT)


@pytest.fixture
def pipe_db(pg_uri):
    import psycopg2
    c = psycopg2.connect(pg_uri); c.autocommit = True; cur = c.cursor()
    cur.execute("""DROP SCHEMA public CASCADE; CREATE SCHEMA public;
        CREATE TABLE ipo_intelligence (
            company_name TEXT, nse_symbol TEXT, symbol TEXT,
            issue_size_cr NUMERIC, ofs_pct NUMERIC, ipo_pe NUMERIC,
            peer_median_pe NUMERIC, final_qib NUMERIC, debt_equity NUMERIC,
            score_band TEXT, listing_gap_pct NUMERIC, listing_date DATE,
            anchor_count INT);
        CREATE TABLE ipo_rhp_intel (
            company_name TEXT, verdict TEXT, quality_gate TEXT,
            requires_further_dd BOOLEAN, auditor_qualified BOOLEAN,
            sebi_action BOOLEAN, criminal_litigation BOOLEAN,
            related_party_concern BOOLEAN, ofs_heavy BOOLEAN,
            promoter_pledge_flag BOOLEAN, customer_concentration_high BOOLEAN,
            contingent_liabilities_material BOOLEAN, numbers_integrity_flag TEXT);
        CREATE TABLE ipo_consolidated (
            company_name TEXT, symbol_final TEXT, listing_date DATE,
            gap_bucket TEXT, issue_size_cr NUMERIC, ipo_pe NUMERIC,
            peer_median_pe NUMERIC, anchor_count INT, listing_open NUMERIC);
        CREATE TABLE price_candles (symbol TEXT, date DATE, open NUMERIC, close NUMERIC);""")
    cur.execute("""INSERT INTO ipo_intelligence
        (company_name, nse_symbol, issue_size_cr, score_band, listing_date, listing_gap_pct)
        VALUES
        ('Strong Listed Ltd', 'STRONG', 3000, 'STRONG', CURRENT_DATE - 20, 10),
        ('Junk Ltd',          'JUNK',    100, 'AVOID',  CURRENT_DATE - 20, 5),
        ('Unlisted Ltd',      'UNL',    1000, NULL,     NULL, NULL)""")
    cur.execute("""INSERT INTO ipo_rhp_intel (company_name, verdict, sebi_action)
        VALUES ('Junk Ltd', 'serious-concerns', TRUE),
               ('Strong Listed Ltd', 'clean', FALSE)""")
    yield pg_uri, c
    c.close()


# ---------------- compute_verdicts main ----------------

def test_verdicts_dry_run_prints_tally_writes_nothing(pipe_db):
    uri, c = pipe_db
    r = _run("compute_verdicts.py", uri)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "verdict tally:" in r.stdout and "AVOID=1" in r.stdout
    cur = c.cursor()
    cur.execute("SELECT to_regclass('ipo_verdicts')")
    assert cur.fetchone()[0] is None                      # table not even created

def test_verdicts_apply_writes_numeric_confidence(pipe_db):
    """Regression 2026-07-17: confidence 'low' crashed an int column. The
    boundary maps high/medium/low -> 90/65/40."""
    uri, c = pipe_db
    r = _run("compute_verdicts.py", uri, "--apply")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "verdicts written" in r.stdout
    cur = c.cursor()
    cur.execute("""SELECT company_name, verdict, confidence FROM ipo_verdicts ORDER BY 1""")
    rows = {r0: (v, cf) for r0, v, cf in cur.fetchall()}
    assert rows["Junk Ltd"][0] == "AVOID"
    assert rows["Unlisted Ltd"][0] == "WATCH"
    assert float(rows["Junk Ltd"][1]) == 90               # AVOID band + rhp verdict -> high -> 90
    assert all(float(cf) in (90, 65, 40) for _, cf in rows.values())

def test_verdicts_apply_upserts_on_rerun(pipe_db):
    uri, c = pipe_db
    _run("compute_verdicts.py", uri, "--apply")
    c.cursor().execute("UPDATE ipo_intelligence SET score_band='STRONG' WHERE company_name='Junk Ltd'")
    # still AVOID via size<200 + rhp — but the point is the upsert path
    r2 = _run("compute_verdicts.py", uri, "--apply")
    assert r2.returncode == 0
    cur = c.cursor(); cur.execute("SELECT COUNT(*) FROM ipo_verdicts")
    assert cur.fetchone()[0] == 3                         # no dup rows


# ---------------- compute_flags main ----------------

def test_flags_apply_writes_arrays_and_counts(pipe_db):
    uri, c = pipe_db
    r = _run("compute_flags.py", uri, "--apply")
    assert r.returncode == 0, r.stdout + r.stderr
    cur = c.cursor()
    cur.execute("""SELECT red_flags, green_checks, red_count, green_count
                   FROM ipo_flags WHERE company_name='Junk Ltd'""")
    red, green, rn, gn = cur.fetchone()
    assert "SEBI action on record" in red
    assert any("junk floor" in f for f in red)
    assert rn == len(red) and gn == len(green)

def test_flags_rerun_updates_not_duplicates(pipe_db):
    uri, c = pipe_db
    _run("compute_flags.py", uri, "--apply")
    c.cursor().execute("UPDATE ipo_rhp_intel SET sebi_action=FALSE WHERE company_name='Junk Ltd'")
    _run("compute_flags.py", uri, "--apply")
    cur = c.cursor()
    cur.execute("SELECT red_flags FROM ipo_flags WHERE company_name='Junk Ltd'")
    assert "SEBI action on record" not in cur.fetchone()[0]   # updated, not stale
    cur.execute("SELECT COUNT(*) FROM ipo_flags")
    assert cur.fetchone()[0] == 3


# ---------------- ipo_score main ----------------

def _seed_consolidated(c):
    cur = c.cursor()
    cur.execute("""INSERT INTO ipo_consolidated VALUES
        ('Strong Listed Ltd','STRONG', CURRENT_DATE - 20, 'MID', 3000, 10, 25, 40, 100),
        ('Nameonly Ltd',     'GHOST',  CURRENT_DATE - 20, 'MID', 3000, 10, 25, 40, 100)""")
    # candles: 10 sessions for STRONG so --backtest has >=3 closes
    for i in range(10):
        cur.execute("INSERT INTO price_candles VALUES ('STRONG', CURRENT_DATE - 20 + %s, 100, %s)",
                    (i, 100 + i))

def test_score_requires_mode_flag(pipe_db):
    uri, _ = pipe_db
    r = _run("ipo_score.py", uri)
    assert r.returncode == 2                              # argparse mutually-exclusive required

def test_score_backtest_reads_only_and_prints_acceptance(pipe_db):
    uri, c = pipe_db
    _seed_consolidated(c)
    r = _run("ipo_score.py", uri, "--backtest")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SCORE v0 BACKTEST" in r.stdout and "ACCEPTANCE:" in r.stdout
    cur = c.cursor()
    cur.execute("""SELECT COUNT(*) FROM information_schema.columns
                   WHERE table_name='ipo_intelligence' AND column_name='ipo_score'""")
    assert cur.fetchone()[0] == 0                         # backtest never ALTERs

def test_score_apply_writes_locked_band_stats(pipe_db):
    """Score 5 (MID+2, mega+2, peer-cheap+1) -> STRONG -> the LOCKED
    (81.4, 9.2) from the approved 2026-07-17 backtest must be written."""
    uri, c = pipe_db
    _seed_consolidated(c)
    r = _run("ipo_score.py", uri, "--apply")
    assert r.returncode == 0, r.stdout + r.stderr
    cur = c.cursor()
    cur.execute("""SELECT ipo_score, score_band, score_expected_win, score_expected_med,
                          score_evidence
                   FROM ipo_intelligence WHERE nse_symbol='STRONG'""")
    s, band, ew, em, ev = cur.fetchone()
    assert (s, band) == (5, "STRONG")
    assert (float(ew), float(em)) == (81.4, 9.2)
    assert "MID gap +2" in ev and ">2000cr +2" in ev and "peer-cheap +1" in ev

def test_score_apply_name_fallback_when_symbol_misses(pipe_db):
    """Consolidated symbol GHOST has no intelligence symbol match -> the
    company_name fallback UPDATE must land the score."""
    uri, c = pipe_db
    _seed_consolidated(c)
    c.cursor().execute("""INSERT INTO ipo_intelligence (company_name, nse_symbol)
                          VALUES ('Nameonly Ltd', NULL)""")
    _run("ipo_score.py", uri, "--apply")
    cur = c.cursor()
    cur.execute("SELECT score_band FROM ipo_intelligence WHERE company_name='Nameonly Ltd'")
    assert cur.fetchone()[0] == "STRONG"
