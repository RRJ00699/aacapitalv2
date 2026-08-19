"""Embedded Postgres for the pipeline suite.

Some pipeline behaviour is only observable against a real server: completeness runs
ORDER BY ... NULLS LAST, ILIKE and array columns, and its whole subject is how many rows
and NULLs exist. Faking the cursor would fake the answer. Mirrors the fixture
_scripts/tests/conftest.py already uses, so DB tests never touch production.
"""
import os

import pytest


@pytest.fixture(scope="session")
def pg_uri():
    try:
        import pgserver
    except ImportError:
        pytest.skip("pgserver not installed (pip install pgserver)")
    import tempfile
    server = pgserver.get_server(tempfile.mkdtemp())
    uri = server.get_uri()
    os.environ["DATABASE_URL"] = uri
    yield uri


# The V2 canonical row shapes completeness reads, as declared by their writers
# (fill_ipo.upsert_ipo, fill_v2.upsert_*) and docs/specifications/V2_SCHEMA.md.
V2_DDL = """
DROP SCHEMA public CASCADE; CREATE SCHEMA public;
CREATE TABLE ipo(
  id BIGINT PRIMARY KEY, isin TEXT, symbol TEXT, name_norm TEXT, name_display TEXT,
  sector TEXT, industry TEXT, is_mainboard BOOLEAN, status TEXT, listing_date DATE,
  kite_token BIGINT, ipomatrix_id TEXT, bse_code TEXT, in_backtest_universe BOOLEAN,
  created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ);
CREATE TABLE ipo_issue(
  ipo_id BIGINT PRIMARY KEY, open_date DATE, close_date DATE, allotment_date DATE,
  band_lo NUMERIC, band_hi NUMERIC, issue_price NUMERIC, lot_size INT, face_value NUMERIC,
  fresh_cr NUMERIC, ofs_cr NUMERIC, issue_size_cr NUMERIC, registrar TEXT,
  brlm_count INT, updated_at TIMESTAMPTZ);
CREATE TABLE listing_outcomes(
  ipo_id BIGINT PRIMARY KEY, listing_open NUMERIC, d1_close NUMERIC, gap_pct NUMERIC,
  pool TEXT, best_close NUMERIC, worst_close NUMERIC, ceiling_20 BOOLEAN,
  hold_positive_vs_open BOOLEAN, winner_35 BOOLEAN, dataset_version TEXT);
CREATE TABLE documents(sha256 TEXT PRIMARY KEY, ipo_id BIGINT, doc_type TEXT);
CREATE TABLE rhp_findings(
  id BIGSERIAL PRIMARY KEY, ipo_id BIGINT, prompt_version TEXT, red_flag_count INT,
  junk_signals TEXT[], analyzed_at TIMESTAMPTZ DEFAULT now());
-- valuation/decisions column lists come from their engines' own INSERTs
-- (score_engine.write_valuation, verdict_engine.write_decision), not from memory.
CREATE TABLE valuation(
  id BIGSERIAL PRIMARY KEY, ipo_id BIGINT, computed_at TIMESTAMPTZ DEFAULT now(),
  engine_version TEXT, pe NUMERIC, pb NUMERIC, roe NUMERIC, roce NUMERIC, de NUMERIC,
  rev_cagr_3y NUMERIC, ofs_pct NUMERIC, peer_median_pe NUMERIC, score NUMERIC,
  score_band TEXT, inputs_used JSONB, missing_inputs TEXT[]);
CREATE TABLE decisions(
  id BIGSERIAL PRIMARY KEY, ipo_id BIGINT, decided_at TIMESTAMPTZ DEFAULT now(),
  engine_version TEXT, fundamental_verdict TEXT, listing_action TEXT,
  reasons JSONB, evidence_refs JSONB);
CREATE TABLE market_candles(ipo_id BIGINT, d DATE, o NUMERIC, h NUMERIC, l NUMERIC,
  c NUMERIC, v BIGINT, PRIMARY KEY(ipo_id, d));
CREATE TABLE market_candles_15m(ipo_id BIGINT, ts TIMESTAMPTZ, o NUMERIC, h NUMERIC,
  l NUMERIC, c NUMERIC, v BIGINT, PRIMARY KEY(ipo_id, ts));
CREATE TABLE financial_statements(
  ipo_id BIGINT, period TEXT, basis TEXT, revenue NUMERIC, total_income NUMERIC,
  ebitda NUMERIC, pat NUMERIC, net_worth NUMERIC, total_debt NUMERIC,
  total_assets NUMERIC, source TEXT, fetched_at TIMESTAMPTZ,
  PRIMARY KEY(ipo_id, period, basis));
CREATE TABLE subscription_snapshots(
  ipo_id BIGINT, captured_at TIMESTAMPTZ, is_final BOOLEAN, qib_x NUMERIC, nii_x NUMERIC,
  bnii_x NUMERIC, snii_x NUMERIC, retail_x NUMERIC, total_x NUMERIC,
  anchor_amount_cr NUMERIC, anchor_count INT, applications_lakh NUMERIC,
  mf_shares_bid NUMERIC, mf_pct_qib NUMERIC, PRIMARY KEY(ipo_id, captured_at));
CREATE TABLE source_facts(
  ipo_id BIGINT, field TEXT, value TEXT, source TEXT, doc_id TEXT, confidence NUMERIC,
  fetched_at TIMESTAMPTZ DEFAULT now());
"""


@pytest.fixture
def v2_db(pg_uri):
    """A fresh V2 schema per test, in the shapes the pipeline writers actually use."""
    import psycopg2
    conn = psycopg2.connect(pg_uri)
    conn.autocommit = True
    conn.cursor().execute(V2_DDL)
    conn.autocommit = False
    yield conn
    conn.close()
