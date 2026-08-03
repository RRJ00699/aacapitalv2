"""Shared fixtures. An embedded Postgres so DB tests NEVER touch production or
require a running server — CI-safe, hermetic."""
import os, pytest

@pytest.fixture(scope="session")
def pg_uri():
    try:
        import pgserver
    except ImportError:
        pytest.skip("pgserver not installed (pip install pgserver)")
    import tempfile
    srv = pgserver.get_server(tempfile.mkdtemp())
    uri = srv.get_uri()
    os.environ["DATABASE_URL"] = uri
    yield uri

@pytest.fixture(scope="session")
def pg_has_tz(pg_uri):
    """Whether the embedded Postgres has IANA tz data. Some pgserver wheels — notably
    the Windows one — ship WITHOUT share/postgresql/timezone, so named zones like
    'Asia/Kolkata' are unresolvable and even querying pg_timezone_names errors. Probed
    once (session-scoped) against the real server, so the result is never a path guess."""
    import psycopg2
    c = psycopg2.connect(pg_uri); cur = c.cursor()
    try:
        cur.execute("SELECT count(*) FROM pg_timezone_names WHERE name = 'Asia/Kolkata'")
        ok = cur.fetchone()[0] > 0
    except Exception:
        ok = False
    finally:
        c.close()
    return ok

@pytest.fixture
def require_pg_tz(pg_has_tz):
    """Skip (with a loud reason) when the embedded Postgres has no tz data. The
    production SQL under test uses now() AT TIME ZONE 'Asia/Kolkata'; on a tz-less
    server it cannot run. NOT a weakened assertion — the test is UNVERIFIED on this
    platform and Linux CI, which has full tzdata, is authoritative for it."""
    if not pg_has_tz:
        pytest.skip("embedded Postgres lacks IANA tz data (Asia/Kolkata unresolvable) — "
                    "unverified here; Linux CI is authoritative")


@pytest.fixture
def clean_db(pg_uri):
    """Fresh base schema per test — the real column shapes the scripts expect."""
    import psycopg2
    c = psycopg2.connect(pg_uri); c.autocommit = True; cur = c.cursor()
    cur.execute("""DROP SCHEMA public CASCADE; CREATE SCHEMA public;
        CREATE TABLE ipo_intelligence (company_name TEXT, nse_symbol TEXT, symbol TEXT, listing_date DATE, close_date DATE, ipo_score INT, score_band TEXT);
        CREATE TABLE ipo_consolidated (company_name TEXT, ipo_open_date DATE, ipo_close_date DATE, listing_date DATE);
        CREATE TABLE ipo_verdicts (company_name TEXT);
        CREATE TABLE ipo_rhp_intel (company_name TEXT);
        CREATE TABLE ipo_research_notes (company TEXT, source TEXT, pdf_path TEXT);
        CREATE TABLE ipo_preopen_book (symbol TEXT, discovery_price NUMERIC, buy_qty BIGINT, sell_qty BIGINT, lean_pct NUMERIC, source TEXT, state_hash TEXT);
        CREATE TABLE ipo_tick_feed (symbol TEXT, recorded_at TIMESTAMPTZ);
        CREATE TABLE ipo_level_analysis (symbol TEXT, trade_date DATE);""")
    c.close()
    return pg_uri
