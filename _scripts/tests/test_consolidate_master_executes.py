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
    for stmt in ("DROP VIEW IF EXISTS ipo_gold", "DROP TABLE IF EXISTS ipo_gold"):
        try: cur.execute(stmt)
        except Exception: pass  # whichever form the previous test left
    cur.execute("""DROP TABLE IF EXISTS ipo_golden, ipo_consolidated, ipo_intelligence,
                   ipo_research_notes, ipo_news, price_candles CASCADE""")
    cur.execute("""CREATE TABLE ipo_consolidated (company_name TEXT, symbol_final TEXT,
        nse_symbol TEXT, symbol TEXT, listing_date DATE, anchor_lock30_date DATE,
        issue_price NUMERIC, ipo_close_date DATE)""")
    cur.execute("""CREATE TABLE ipo_intelligence (company_name TEXT, isin TEXT,
        nse_symbol TEXT, symbol TEXT, ipo_close_date DATE, listing_date DATE,
        lot_size INT, allotment_date DATE, mcap_offer NUMERIC, ronw NUMERIC,
        ipo_pb NUMERIC, promoter_holding_post NUMERIC, registrar TEXT,
        sub_day3_x NUMERIC, total_applications BIGINT)""")
    # PROD TRUTH: ipo_research_notes has NO stored_at (predates it) — id SERIAL
    # is the only recency column (see schema_sync's 2026-07-18 note).
    cur.execute("""CREATE TABLE ipo_research_notes (company TEXT, source TEXT,
        full_json JSONB, id SERIAL)""")
    # RHP Sonnet's REAL home (owner evidence: research_notes has zero RHP rows)
    cur.execute("""CREATE TABLE ipo_rhp_intel (company_name TEXT PRIMARY KEY,
        full_json JSONB, stored_at TIMESTAMPTZ DEFAULT NOW())""")
    cur.execute("""CREATE TABLE ipo_news (company_name TEXT, headline TEXT, publisher TEXT,
        url TEXT, source TEXT DEFAULT 'rss', fetch_status TEXT DEFAULT 'ok',
        is_current BOOLEAN DEFAULT TRUE, created_at TIMESTAMPTZ DEFAULT NOW())""")
    cur.execute("CREATE TABLE price_candles (symbol TEXT, date DATE, open NUMERIC, high NUMERIC, low NUMERIC, close NUMERIC, volume BIGINT)")
    cur.execute("CREATE TABLE nse_issue_info (symbol TEXT PRIMARY KEY, raw_json JSONB, anchor_portion_shares BIGINT, fetched_at TIMESTAMPTZ)")
    cur.execute("""CREATE TABLE ipo_golden (company_key TEXT PRIMARY KEY, company_name TEXT,
        nse_symbol TEXT, isin TEXT, lot_size INT, allotment_date DATE, mcap_cr NUMERIC,
        price_to_book NUMERIC, promoter_post_pct NUMERIC, registrar_name TEXT,
        anchor_lock30_date DATE, anchor_lock90_date DATE, ebitda_margin NUMERIC,
        bnii_x NUMERIC, snii_x NUMERIC, anchor_amount_cr NUMERIC,
        final_qib NUMERIC, final_nii NUMERIC, final_retail NUMERIC, final_total NUMERIC,
        industry TEXT, nse_listing_date DATE,
        ronw NUMERIC, sub_day3_x NUMERIC, total_applications BIGINT,
        rhp_sonnet_json JSONB, sbi_haiku_json JSONB,
        street_headline TEXT, street_publisher TEXT, street_url TEXT,
        candles_json JSONB, golden_filled_at TIMESTAMPTZ)""")
    cur.execute("""INSERT INTO ipo_consolidated VALUES
        ('SBI Funds Management Ltd.','SBIFUNDS',NULL,'SBIFUNDS','2026-07-10',NULL,574,'2026-07-16')""")
    cur.execute("""INSERT INTO ipo_intelligence VALUES
        ('SBI Funds Management Ltd.','INE640G01020','SBIFUNDS','SBIFUNDS','2026-07-16','2026-07-10',26,'2026-07-17',116913.9,43.02,19.6,88.0,'Kfin Technologies',41.66,6380000)""")  # listing 07-10 < close 07-16 = the contradiction class; NSE corrects to 07-21
    cur.execute("""INSERT INTO ipo_research_notes (company, source, full_json) VALUES
        ('SBI Funds Management Ltd.','SBI','{"rating":"SUBSCRIBE"}')""")
    cur.execute("""INSERT INTO ipo_rhp_intel (company_name, full_json)
        VALUES ('SBI Funds Management Ltd.', '{"one_line":"clean"}')""")
    cur.execute("""INSERT INTO ipo_news (company_name, headline, publisher, url, source) VALUES
        ('SBI Funds Management Ltd.','SBI Funds debuts above issue','Reuters','https://reuters.com/x','manual'),
        ('SBI Funds Management Ltd.','<paste exact headline>','Reuters','<paste url>','manual')""")
    cur.execute("""INSERT INTO price_candles VALUES
        ('SBIFUNDS','2026-07-21',613.3,641,600,609.75,90000000),
        ('SBIFUNDS','2026-07-22',610,615,601,604,30000000),
        ('SBIFUNDS','2026-07-23',700,600,650,900,1)""")  # impossible OHLC — must be excluded
    # REAL payload shape from the owner's banked LASERPOWER/FEDFINA slices
    import json as _j
    payload = {"metaInfo": {"isin": "INE640G01020", "industry": "Asset Management",
                            "listingDate": "2026-07-21"},
               "issueInfo": {"issueSize": "Offer including Anchor investor portion of 4,63,93,095 Equity Shares"},
               "activeCat": {"dataList": [
                 {"srNo": "Sr.No.", "category": "Category", "noOfTotalMeant": "No. of times"},
                 {"srNo": "1", "category": "QIB", "noOfTotalMeant": "140.11"},
                 {"srNo": "2", "category": "NII", "noOfTotalMeant": "22.51"},
                 {"srNo": "2.1", "category": "bNII", "noOfTotalMeant": "26.01"},
                 {"srNo": "2.2", "category": "sNII", "noOfTotalMeant": "15.51"},
                 {"srNo": "3", "category": "Retail", "noOfTotalMeant": "3.59"},
                 {"srNo": "Total", "category": "Total", "noOfTotalMeant": "41.66"}]}}
    cur.execute("INSERT INTO nse_issue_info VALUES ('SBIFUNDS', %s, NULL, NOW())", (_j.dumps(payload),))
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
                          price_to_book, promoter_post_pct, registrar_name,
                          rhp_sonnet_json->>'one_line', sbi_haiku_json->>'rating',
                          street_headline, json_array_length(candles_json::json)
                   FROM ipo_golden""")
    (isin, lot, mcap, ronw, d3, apps, pb, ppost, reg, sonnet, haiku, head, days) = cur.fetchone()
    assert isin == "INE640G01020" and lot == 26 and float(mcap) == 116913.9
    assert float(pb) == 19.6 and float(ppost) == 88.0 and reg == "Kfin Technologies", \
        "REAL intelligence column names (mcap_offer/ipo_pb/promoter_holding_post/registrar) feed golden"
    assert float(ronw) == 43.02 and float(d3) == 41.66 and apps == 6380000
    assert sonnet == "clean" and haiku == "SUBSCRIBE"
    assert head == "SBI Funds debuts above issue", "placeholder row must lose to the real one"
    assert days == 2, "impossible-OHLC row excluded; real sessions kept"
    cur.execute("""SELECT final_qib, final_retail, final_total, bnii_x, snii_x,
                          industry, nse_listing_date, anchor_amount_cr FROM ipo_golden""")
    (fq, fr, ft, bn, sn, ind, nld, aac) = cur.fetchone()
    assert float(fq) == 140.11 and float(fr) == 3.59 and float(ft) == 41.66, "activeCat finals mined"
    assert float(bn) == 26.01 and float(sn) == 15.51, "bNII/sNII sub-rows mined"
    assert ind == "Asset Management" and str(nld) == "2026-07-21", "metaInfo mined"
    cur.execute("SELECT listing_date FROM ipo_intelligence")
    assert str(cur.fetchone()[0]) == "2026-07-21", \
        "close_after_listing contradiction corrected from NSE listing date"
    assert aac is not None and abs(float(aac) - round(46393095 * 574 / 1e7, 2)) < 0.01, \
        "broadened anchor regex + amount derived from shares * issue_price"
    cur.execute("SELECT anchor_lock30_date, anchor_lock90_date FROM ipo_golden")
    l30, l90 = cur.fetchone()
    assert str(l30) == "2026-08-09" and str(l90) == "2026-10-08", \
        "lock dates derived listing+30/90 when vendor never supplied them"
    # second run: idempotent, fill-empty (no duplicate seeding, values stable)
    importlib.reload(consolidate_master)
    assert consolidate_master.main() == 0
    cur.execute("SELECT COUNT(*) FROM ipo_golden"); assert cur.fetchone()[0] == 1
    conn.close()
