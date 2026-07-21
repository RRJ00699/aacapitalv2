#!/usr/bin/env python3
"""Hotfixes for the owner's 2026-07-21 23:47 IST run: scope bug, spend gate,
mid-run board. Mapping EXECUTED so scope bugs can't ship again."""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REPO = os.path.dirname(ROOT)

PAYLOAD = {"data": {
    "issue_details": {"price_band_lower": 404, "price_band_upper": 425, "final_price": 425,
                      "ttl_ofs_amt_cr": "1,101.28", "ttl_fresh_issue_amt_cr": "0",
                      "lead_managers": [{"comp_short_name": "X Cap"}], "registrar": {"name": "R"}},
    "kpi": {"pe_ratio": 23.1, "price_to_book": 4.2, "roe": 36.8, "debt_equity": 0.1},
    "anchor": {"investors": [{"investor_name": "A Fund"}], "total_amount_cr": 330, "total_issue_percentage": 30},
    "subscription": {"summary": {"qib": 1.2, "nii": 0.8, "rii": 0.5, "total": 0.9}},
    "pre_post_holding": {}, "market_cap": {"at_offer_price": 5000},
    "listing": {"exchanges": [{"exchange": "NSE", "open": 500, "high": 510, "low": 495, "close": 505}]},
}}


def test_ipomatrix_extract_executes_without_argparse_in_scope():
    """The shipped bug: extract() referenced the argparse namespace ->
    NameError on BOTH IPOMatrix steps every run. extract() must be pure.
    Subprocess-executed because the module rewraps sys.stdout on import
    (Windows shim) — same isolation the pipeline gives it."""
    prog = (
        "import importlib.util, json, sys\n"
        f"spec = importlib.util.spec_from_file_location('im', {json.dumps(os.path.join(ROOT, 'ipomatrix_ingest.py'))})\n"
        "im = importlib.util.module_from_spec(spec); spec.loader.exec_module(im)\n"
        f"payload = json.loads({json.dumps(json.dumps(PAYLOAD))})\n"
        "f = im.extract(payload)\n"
        "im.discover_unmapped(payload['data'])\n"
        "print('RESULT ' + json.dumps({'pe': f['ipo_pe'], 'bh': f['price_band_high'],"
        " 'ac': f['anchor_count'], 'lo': f['listing_open']}))\n"
    )
    r = subprocess.run([sys.executable, "-c", prog], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[:400]
    line = [l for l in r.stdout.splitlines() if l.startswith("RESULT ")][-1]
    got = json.loads(line[len("RESULT "):])
    assert got == {"pe": 23.1, "bh": 425, "ac": 1, "lo": 500}


def test_extract_source_has_no_cli_reference():
    src = open(os.path.join(ROOT, "ipomatrix_ingest.py"), encoding="utf-8").read()
    body = src[src.index("def extract(js):"):src.index("def resolve_ids")]
    assert not re.search(r"\ba\.", body), "extract() must not touch the argparse namespace"


def test_haiku_spend_is_eligibility_gated():
    """LOCKED rule gates the SPEND: no Haiku dollars for SME/<200cr notes.
    Same rule text as the three feeds (one rule everywhere)."""
    src = open(os.path.join(ROOT, "sbi_haiku_extract.py"), encoding="utf-8").read()
    assert "COALESCE(i.is_sme, false) = false" in src
    assert "i.issue_size_cr IS NULL OR i.issue_size_cr >= 200" in src
    todo = src[src.index("TODO_SQL"):src.index("ORDER BY i.listing_date")]
    assert "is_sme" in todo and "issue_size_cr" in todo, "the gate must be inside the WORK query"


def test_stepboard_suppresses_missed_mid_run():
    src = open(os.path.join(REPO, "app", "dashboard", "settings", "page.tsx"), encoding="utf-8").read()
    assert "inProgress" in src and "RUN IN PROGRESS" in src
    assert "inProgress?[]:expected.filter" in src.replace(" ", ""), "missed lane must be empty while running"


def test_runbook_documents_kite_maintenance_window():
    src = open(os.path.join(REPO, "docs", "VM_CRON_RUNBOOK.md"), encoding="utf-8").read()
    assert "23:30" in src and "market regime" in src


def test_haiku_gate_excludes_sme_and_small_on_real_postgres(pg_uri):
    """EXECUTED: an SME note and a <200cr note are NOT work; a mainboard
    NULL-size note IS (NULL stays eligible per the locked rule)."""
    import importlib.util, psycopg2
    spec = importlib.util.spec_from_file_location("ss", os.path.join(ROOT, "schema_sync.py"))
    ss = importlib.util.module_from_spec(spec); spec.loader.exec_module(ss)
    c = psycopg2.connect(pg_uri); c.autocommit = True; cur = c.cursor()
    for t in ("ipo_research_notes", "ipo_intelligence", "sbi_haiku_run_log"):
        cur.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    cur.execute("CREATE TABLE ipo_intelligence (id SERIAL PRIMARY KEY, company_name TEXT, listing_date DATE, close_date DATE)")
    cur.execute("CREATE TABLE ipo_research_notes (id SERIAL PRIMARY KEY, source TEXT, company TEXT, pdf_path TEXT, full_json JSONB)")
    for stmt in ss.DDL:
        try: cur.execute(stmt)
        except Exception: pass
    rows = [("Mainboard Null Size Ltd", None, False), ("Tiny Ltd", 126, False), ("SME Corp Ltd", 300, True)]
    for name, size, sme in rows:
        cur.execute("INSERT INTO ipo_intelligence (company_name, listing_date, issue_size_cr, is_sme) VALUES (%s, CURRENT_DATE + 7, %s, %s)", (name, size, sme))
        cur.execute("INSERT INTO ipo_research_notes (source, company, pdf_path) VALUES ('SBI', %s, '/tmp/x.pdf')", (name,))
    src = open(os.path.join(ROOT, "sbi_haiku_extract.py"), encoding="utf-8").read()
    todo = src.split('TODO_SQL = r"""')[1].split('"""')[0]
    cur.execute(todo)
    names = sorted(r[1] for r in cur.fetchall())
    assert names == ["Mainboard Null Size Ltd"], f"gate leaked: {names}"
    c.close()


def test_rhp_auto_final_line_names_failed_substep():
    """The board truncates step output; rhp_auto's LAST line must name the
    failing substep + real stderr so reds are diagnosable from the phone."""
    src = open(os.path.join(ROOT, "rhp_auto.py"), encoding="utf-8").read()
    assert 'LAST_ERR["label"] = label' in src
    assert 'FAILED substep [' in src
    assert src.index("FAILED substep [") > src.index("def run(label, args):")


def test_kite_skips_are_recorded_not_silent():
    """08:30 runs always have a stale token (refresh crons at 08:45): the
    four candle steps AND sync_trade_journal must record green skip rows —
    no false MISSED, no traceback."""
    src = open(os.path.join(ROOT, "run_ipo_pipeline_lean.py"), encoding="utf-8").read()
    assert src.count("skipped — Kite token stale (expected on the 08:30 run)") >= 2
    guarded = src.split("if kite_ok:")
    assert len(guarded) >= 3, "journal must sit behind its own kite_ok guard"
    assert "sync_trade_journal.py" in guarded[2] or "sync_trade_journal.py" in guarded[-1]
    for nm in ("candles: in-window daily sync",
               "listing-day fields (kite)", "derive listing_open"):
        assert src.count(f'"{nm}"') >= 2, f"skip row missing for {nm}"


def test_core_ipo_scope_no_universe_candles():
    """LOCKED scope (owner 2026-07-21): Core IPO platform — no 1400-stock
    universe sync in the pipeline, no Admin button, no EXPECTED entry. The
    in-window IPO sync remains the only candle producer."""
    lean = open(os.path.join(ROOT, "run_ipo_pipeline_lean.py"), encoding="utf-8").read()
    assert 'step("candles: full NSE universe"' not in lean
    assert 'step("candles: in-window daily sync"' in lean
    assert '"universe_candles"' not in open(os.path.join(ROOT, "job_runner.py"), encoding="utf-8").read()
    route = open(os.path.join(REPO, "app", "api", "admin", "pipeline-steps", "route.ts"), encoding="utf-8").read()
    assert "full NSE universe" not in route
