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
