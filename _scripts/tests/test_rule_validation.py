#!/usr/bin/env python3
"""Rule Validation Engine EXECUTED against real Postgres with a synthetic
golden universe whose outcomes are known by construction."""
import importlib
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))


def _candles(open_px, best_close, low):
    return json.dumps([{"d": "2026-01-01", "o": open_px, "h": best_close, "l": low, "c": best_close, "v": 1}])


def test_engine_runs_stores_and_ranks(pg_uri, monkeypatch, capsys):
    import psycopg2
    conn = psycopg2.connect(pg_uri); conn.autocommit = True; cur = conn.cursor()
    for stmt in ("DROP VIEW IF EXISTS ipo_gold", "DROP TABLE IF EXISTS ipo_gold"):
        try: cur.execute(stmt)
        except Exception: pass  # whichever form the previous test left
    cur.execute("DROP TABLE IF EXISTS rule_validation_results")
    # engine reads the one object; a TABLE named ipo_gold works identically
    cur.execute("""CREATE TABLE ipo_gold (company_name TEXT, listing_date DATE,
        anchor_count INT, anchor_amount_cr NUMERIC, issue_size_cr NUMERIC, ipo_pe NUMERIC, final_qib NUMERIC,
        final_total NUMERIC, bnii_x NUMERIC, listing_gap_pct NUMERIC, price_to_book NUMERIC, ofs_pct NUMERIC,
        score_band TEXT, issue_price NUMERIC, is_sme BOOLEAN, candles_json JSONB)""")
    cur.execute("""CREATE TABLE rule_validation_results (id BIGSERIAL PRIMARY KEY,
        rule_id TEXT, rule_version TEXT, backtest_version TEXT, dataset TEXT,
        sql_filter TEXT, rule_filter TEXT, date_range TEXT, n INT, win_rate NUMERIC,
        avg_return NUMERIC, median_return NUMERIC, max_drawdown NUMERIC,
        expectancy NUMERIC, p_vs_baseline NUMERIC, beats_baseline BOOLEAN,
        baseline_win_rate NUMERIC, universe_n INT, run_at TIMESTAMPTZ)""")
    # 40 IPOs: 30 with >=50 anchors ALL winners (+10%); 10 with 5 anchors ALL
    # losers (-8%) -> anchors rules must beat the 75% baseline; AVOID band = losers.
    for i in range(30):
        cur.execute("INSERT INTO ipo_gold VALUES (%s,'2025-01-01',60,900,3000,25,80,50,45,22,9,0.4,'STRONG',100,false,%s)",
                    (f"W{i}", _candles(100, 110, 98)))
    for i in range(10):
        cur.execute("INSERT INTO ipo_gold VALUES (%s,'2025-06-01',5,30,300,90,2,3,2,-4,3,0,'AVOID',100,false,%s)",
                    (f"L{i}", _candles(100, 92, 88)))
    conn.close()

    monkeypatch.setenv("DATABASE_URL", pg_uri)
    monkeypatch.setattr(sys, "argv", ["rule_validation.py", "--store"])
    import rule_validation
    importlib.reload(rule_validation)
    assert rule_validation.main() == 0
    out = capsys.readouterr().out
    assert "BASELINE win 75.0%" in out
    assert "rv1-2026-07-22" in out and "ipo_gold" in out, "provenance printed"

    conn = psycopg2.connect(pg_uri); cur = conn.cursor()
    cur.execute("""SELECT rule_id, n, win_rate, beats_baseline, sql_filter, backtest_version
                   FROM rule_validation_results""")
    got = {r[0]: r for r in cur.fetchall()}
    assert got["anchors_50plus"][1] == 30 and float(got["anchors_50plus"][2]) == 1.0
    assert got["anchors_50plus"][3] is True, "100% win over 75% baseline (n=30) must beat"
    assert got["band_avoid_skip"][1] == 10 and float(got["band_avoid_skip"][2]) == 0.0
    assert got["band_avoid_skip"][3] is False
    assert "REIT|InvIT" in got["anchors_50plus"][4], "filters recorded verbatim"
    assert "2016-01-01" in got["anchors_50plus"][4], "DECADE LOCK rides in provenance (owner 2026-07-24)"
    assert got["anchors_50plus"][5] == "rv1-2026-07-22"
    conn.close()


SCRIPTS = __import__("os").path.join(__import__("os").path.dirname(__file__), "..")


def test_pattern_mining_runs_and_reports(pg_uri, monkeypatch):
    """Executed smoke: the winners-profile miner runs against a real Postgres
    ipo_gold and prints the factor table (owner ask 2026-07-22).

    Uses the shared pg_uri fixture so environments without pgserver skip with
    the suite's standard explicit reason instead of failing at import time.
    """
    import psycopg2, subprocess, sys, os
    uri = pg_uri
    conn = psycopg2.connect(uri); conn.autocommit = True; cur = conn.cursor()
    cur.execute("""CREATE TABLE ipo_gold (company_name TEXT, listing_date DATE,
        anchor_count INT, anchor_amount_cr NUMERIC, issue_size_cr NUMERIC, ipo_pe NUMERIC,
        final_qib NUMERIC, final_nii NUMERIC, final_retail NUMERIC, final_total NUMERIC,
        bnii_x NUMERIC, snii_x NUMERIC, peer_median_pe NUMERIC, ronw NUMERIC, roe NUMERIC,
        revenue_cagr_3y NUMERIC, profit_cagr_3y NUMERIC, debt_equity NUMERIC,
        ebitda_margin NUMERIC, promoter_post_pct NUMERIC, ofs_pct NUMERIC,
        listing_gap_pct NUMERIC, price_to_book NUMERIC, quality_score NUMERIC,
        industry TEXT, structure_type TEXT, score_band TEXT, issue_price NUMERIC,
        is_sme BOOLEAN, candles_json JSONB)""")
    import json as _j
    up = _j.dumps([{"d": "2025-01-02", "o": 100, "h": 112, "l": 99, "c": 111, "v": 1}])  # prod short keys
    dn = _j.dumps([{"d": "2025-01-02", "o": 100, "h": 101, "l": 88, "c": 90, "v": 1}])
    for i in range(35):
        cur.execute("""INSERT INTO ipo_gold (company_name, listing_date, anchor_count,
            anchor_amount_cr, issue_size_cr, final_qib, ipo_pe, industry, issue_price,
            is_sme, candles_json) VALUES (%s,'2025-01-01',%s,%s,1000,%s,%s,%s,100,false,%s)""",
            (f"W{i}", 60, 350, 80, 25, "Chemicals", up))
    for i in range(35):
        cur.execute("""INSERT INTO ipo_gold (company_name, listing_date, anchor_count,
            anchor_amount_cr, issue_size_cr, final_qib, ipo_pe, industry, issue_price,
            is_sme, candles_json) VALUES (%s,'2025-06-01',%s,%s,1000,%s,%s,%s,100,false,%s)""",
            (f"L{i}", 10, 60, 3, 95, "Realty", dn))
    conn.close()
    env = dict(os.environ, DATABASE_URL=uri)
    out = subprocess.run([sys.executable, os.path.join(SCRIPTS, "pattern_mining.py")],
                         capture_output=True, text=True, env=env)
    assert out.returncode == 0, out.stderr[-800:]
    assert "WINNERS 35" in out.stdout and "QIB subscription x" in out.stdout
    assert "Chemicals" in out.stdout and "<<" in out.stdout, out.stdout[-600:]
