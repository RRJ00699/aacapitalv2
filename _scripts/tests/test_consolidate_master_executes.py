#!/usr/bin/env python3
"""consolidate_master EXECUTED end-to-end against real Postgres — the test
class that would have caught the NameError('cast') prod failure: every SQL
string is actually built and run, every fill path exercised."""
import importlib
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))


def test_full_job_runs_and_fills_golden(pg_uri, monkeypatch, capsys):
    import psycopg2
    conn = psycopg2.connect(pg_uri); conn.autocommit = True; cur = conn.cursor()
    cur.execute("DROP VIEW IF EXISTS ipo_gold")
    cur.execute("""DROP TABLE IF EXISTS ipo_golden, ipo_consolidated, ipo_intelligence,
                   ipo_research_notes, ipo_news, price_candles CASCADE""")
    cur.execute("""CREATE TABLE ipo_consolidated (company_name TEXT, symbol_final TEXT,
        nse_symbol TEXT, symbol TEXT, listing_date DATE, anchor_lock30_date DATE)""")
    cur.execute("""CREATE TABLE ipo_intelligence (company_name TEXT, isin TEXT,
        lot_size INT, allotment_date DATE, mcap_cr NUMERIC, ronw NUMERIC,
        sub_day3_x NUMERIC, total_applications BIGINT)""")
    cur.execute("""CREATE TABLE ipo_research_notes (company TEXT, source TEXT,
        full_json JSONB, stored_at TIMESTAMPTZ DEFAULT NOW())""")
    cur.execute("""CREATE TABLE ipo_news (company_name TEXT, headline TEXT, publisher TEXT,
        url TEXT, source TEXT DEFAULT 'rss', fetch_status TEXT DEFAULT 'ok',
        is_current BOOLEAN DEFAULT TRUE, created_at TIMESTAMPTZ DEFAULT NOW())""")
    cur.execute("CREATE TABLE price_candles (symbol TEXT, date DATE, open NUMERIC, high NUMERIC, low NUMERIC, close NUMERIC, volume BIGINT)")
    cur.execute("""CREATE TABLE ipo_golden (company_key TEXT PRIMARY KEY, company_name TEXT,
        nse_symbol TEXT, isin TEXT, lot_size INT, allotment_date DATE, mcap_cr NUMERIC,
        ronw NUMERIC, sub_day3_x NUMERIC, total_applications BIGINT,
        rhp_sonnet_json JSONB, sbi_haiku_json JSONB,
        street_headline TEXT, street_publisher TEXT, street_url TEXT,
        candles_json JSONB, golden_filled_at TIMESTAMPTZ)""")
    cur.execute("""INSERT INTO ipo_consolidated VALUES
        ('SBI Funds Management Ltd.','SBIFUNDS',NULL,'SBIFUNDS','2026-07-21',NULL)""")
    cur.execute("""INSERT INTO ipo_intelligence VALUES
        ('SBI Funds Management Ltd.','INE640G01020',26,'2026-07-17',116900,43.02,41.66,6380000)""")
    cur.execute("""INSERT INTO ipo_research_notes (company, source, full_json) VALUES
        ('SBI Funds Management Ltd.','RHP_SONNET','{"one_line":"clean"}'),
        ('SBI Funds Management Ltd.','SBI','{"rating":"SUBSCRIBE"}')""")
    cur.execute("""INSERT INTO ipo_news (company_name, headline, publisher, url, source) VALUES
        ('SBI Funds Management Ltd.','SBI Funds debuts above issue','Reuters','https://reuters.com/x','manual'),
        ('SBI Funds Management Ltd.','<paste exact headline>','Reuters','<paste url>','manual')""")
    cur.execute("""INSERT INTO price_candles VALUES
        ('SBIFUNDS','2026-07-21',613.3,641,600,609.75,90000000),
        ('SBIFUNDS','2026-07-22',610,615,601,604,30000000)""")
    conn.close()

    monkeypatch.setenv("DATABASE_URL", pg_uri)
    monkeypatch.setattr(sys, "argv", ["consolidate_master.py", "--apply"])
    import consolidate_master
    importlib.reload(consolidate_master)
    assert consolidate_master.main() == 0   # would have raised NameError before
    out = capsys.readouterr().out
    assert "COMMITTED" in out

    conn = psycopg2.connect(pg_uri); cur = conn.cursor()
    cur.execute("""SELECT isin, lot_size, mcap_cr, ronw, sub_day3_x, total_applications,
                          rhp_sonnet_json->>'one_line', sbi_haiku_json->>'rating',
                          street_headline, json_array_length(candles_json::json)
                   FROM ipo_golden""")
    (isin, lot, mcap, ronw, d3, apps, sonnet, haiku, head, days) = cur.fetchone()
    assert isin == "INE640G01020" and lot == 26 and float(mcap) == 116900
    assert float(ronw) == 43.02 and float(d3) == 41.66 and apps == 6380000
    assert sonnet == "clean" and haiku == "SUBSCRIBE"
    assert head == "SBI Funds debuts above issue", "placeholder row must lose to the real one"
    assert days == 2, "candles_json materialized listing-window OHLCV"
    # second run: idempotent, fill-empty (no duplicate seeding, values stable)
    importlib.reload(consolidate_master)
    assert consolidate_master.main() == 0
    cur.execute("SELECT COUNT(*) FROM ipo_golden"); assert cur.fetchone()[0] == 1
    conn.close()
