"""Integration tests for _scripts/sync_issue_details.py — the fix for the
SCHEMA.md pipeline gap (NULL sector/nse_symbol -> peer P/E + fair value
silently fail; root cause 2026-07-15).

Verifies every rule the script claims, as a subprocess vs embedded PG:
  RULE 2  strong-key only: isin exact join, NULL isin never matches
  RULE 3  fill-empty-only: existing values never overwritten
  dry-run default: no writes without --apply
"""
import os, sys, subprocess, pathlib
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration


def _run(uri, *args):
    env = dict(os.environ, DATABASE_URL=uri)
    env.pop("NEON_DATABASE_URL", None)
    return subprocess.run([sys.executable, str(ROOT / "_scripts" / "sync_issue_details.py"), *args],
                          capture_output=True, text=True, env=env, timeout=60)


@pytest.fixture
def sync_db(pg_uri):
    import psycopg2
    c = psycopg2.connect(pg_uri); c.autocommit = True; cur = c.cursor()
    cur.execute("""DROP SCHEMA public CASCADE; CREATE SCHEMA public;
        CREATE TABLE ipo_intelligence (company_name TEXT, isin TEXT,
            nse_symbol TEXT, sector TEXT, eps_post NUMERIC);
        CREATE TABLE ipo_issue_details (company TEXT, isin TEXT,
            nse_symbol TEXT, industry TEXT, eps_post NUMERIC);""")
    yield pg_uri, c
    c.close()


def _rows(c):
    cur = c.cursor()
    cur.execute("SELECT company_name, nse_symbol, sector, eps_post FROM ipo_intelligence ORDER BY 1")
    return {r[0]: r[1:] for r in cur.fetchall()}


def test_dry_run_default_writes_nothing(sync_db):
    uri, c = sync_db
    cur = c.cursor()
    cur.execute("""INSERT INTO ipo_intelligence VALUES ('Gap Ltd','INE001',NULL,NULL,NULL)""")
    cur.execute("""INSERT INTO ipo_issue_details VALUES ('Gap Ltd','INE001','GAP','Chemicals',12.5)""")
    r = _run(uri)
    assert r.returncode == 0
    assert "would fill  nse_symbol=1  sector=1  eps_post=1" in r.stdout
    assert "DRY RUN" in r.stdout
    assert _rows(c)["Gap Ltd"] == (None, None, None)      # untouched

def test_apply_fills_all_three_fields(sync_db):
    uri, c = sync_db
    cur = c.cursor()
    cur.execute("""INSERT INTO ipo_intelligence VALUES ('Gap Ltd','INE001',NULL,NULL,NULL)""")
    cur.execute("""INSERT INTO ipo_issue_details VALUES ('Gap Ltd','INE001','GAP','Chemicals',12.5)""")
    r = _run(uri, "--apply")
    assert r.returncode == 0 and "1 ipo_intelligence row(s) updated" in r.stdout
    sym, sec, eps = _rows(c)["Gap Ltd"]
    assert (sym, sec, float(eps)) == ("GAP", "Chemicals", 12.5)

def test_rule3_fill_empty_only_never_overwrites(sync_db):
    """RULE 3: an existing good value survives even when details disagree."""
    uri, c = sync_db
    cur = c.cursor()
    cur.execute("""INSERT INTO ipo_intelligence VALUES
        ('Partial Ltd','INE002','KEEPME','Pharma',NULL)""")
    cur.execute("""INSERT INTO ipo_issue_details VALUES
        ('Partial Ltd','INE002','CLOBBER','WrongSector',9.9)""")
    _run(uri, "--apply")
    sym, sec, eps = _rows(c)["Partial Ltd"]
    assert sym == "KEEPME" and sec == "Pharma"            # not clobbered
    assert float(eps) == 9.9                              # only the NULL filled

def test_sector_unknown_treated_as_empty(sync_db):
    """'Unknown' is a placeholder, not data — it must be replaceable."""
    uri, c = sync_db
    cur = c.cursor()
    cur.execute("""INSERT INTO ipo_intelligence VALUES ('Unk Ltd','INE003','SYM','Unknown',1)""")
    cur.execute("""INSERT INTO ipo_issue_details VALUES ('Unk Ltd','INE003','SYM','Realty',1)""")
    _run(uri, "--apply")
    assert _rows(c)["Unk Ltd"][1] == "Realty"

def test_rule2_null_isin_never_matches(sync_db):
    """RULE 2: strong key only. NULL isin on either side = no sync, even for
    an identical company name — name matching is exactly what's forbidden."""
    uri, c = sync_db
    cur = c.cursor()
    cur.execute("""INSERT INTO ipo_intelligence VALUES ('NoIsin Ltd',NULL,NULL,NULL,NULL)""")
    cur.execute("""INSERT INTO ipo_issue_details VALUES ('NoIsin Ltd',NULL,'LEAK','Leaky',7)""")
    r = _run(uri, "--apply")
    assert "0 ipo_intelligence row(s) updated" in r.stdout
    assert _rows(c)["NoIsin Ltd"] == (None, None, None)

def test_rule2_wrong_isin_never_matches(sync_db):
    """The CSM->MTAR failure shape: same-ish names, different isin = no cross-fill."""
    uri, c = sync_db
    cur = c.cursor()
    cur.execute("""INSERT INTO ipo_intelligence VALUES ('CSM Tech Ltd','INE100',NULL,NULL,NULL)""")
    cur.execute("""INSERT INTO ipo_issue_details VALUES ('CSM Tech Ltd','INE999','MTAR','Defence',5)""")
    _run(uri, "--apply")
    assert _rows(c)["CSM Tech Ltd"] == (None, None, None)

def test_missing_table_exits_loud(sync_db):
    uri, c = sync_db
    c.cursor().execute("DROP TABLE ipo_issue_details")
    r = _run(uri)
    assert r.returncode != 0 and "missing" in (r.stdout + r.stderr)

def test_idempotent_second_apply_zero_rows(sync_db):
    uri, c = sync_db
    cur = c.cursor()
    cur.execute("""INSERT INTO ipo_intelligence VALUES ('Gap Ltd','INE001',NULL,NULL,NULL)""")
    cur.execute("""INSERT INTO ipo_issue_details VALUES ('Gap Ltd','INE001','GAP','Chemicals',12.5)""")
    _run(uri, "--apply")
    r2 = _run(uri, "--apply")
    assert "0 ipo_intelligence row(s) updated" in r2.stdout
