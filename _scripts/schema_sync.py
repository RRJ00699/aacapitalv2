#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""schema_sync.py — THE single owner of schema evolution (audit action #4).
Every ALTER/CREATE the platform needs, idempotent, run FIRST in the lean
pipeline. Kills the phantom-column class (#159/#184/#198: route ships before
column exists -> 500). New column? Add HERE, never inline in a feature script.
Run:  venv/bin/python _scripts/schema_sync.py
"""
import os
import psycopg2

DDL = [
    # ── ipo_intelligence: derived/score/quality columns ──
    "ALTER TABLE ipo_intelligence ADD COLUMN IF NOT EXISTS eps_source TEXT",
    "ALTER TABLE ipo_intelligence ADD COLUMN IF NOT EXISTS quality_score NUMERIC",
    "ALTER TABLE ipo_intelligence ADD COLUMN IF NOT EXISTS quality_conf NUMERIC",
    "ALTER TABLE ipo_intelligence ADD COLUMN IF NOT EXISTS ipo_score INT",
    "ALTER TABLE ipo_intelligence ADD COLUMN IF NOT EXISTS score_band TEXT",
    "ALTER TABLE ipo_intelligence ADD COLUMN IF NOT EXISTS score_evidence TEXT",
    "ALTER TABLE ipo_intelligence ADD COLUMN IF NOT EXISTS score_expected_win NUMERIC",
    "ALTER TABLE ipo_intelligence ADD COLUMN IF NOT EXISTS score_expected_med NUMERIC",
    # ── ipo_research_notes: Haiku extraction ──
    "ALTER TABLE ipo_research_notes ADD COLUMN IF NOT EXISTS full_json JSONB",
    "ALTER TABLE ipo_research_notes ADD COLUMN IF NOT EXISTS one_line TEXT",
    "ALTER TABLE ipo_research_notes ADD COLUMN IF NOT EXISTS ai_model TEXT",
    # ── observability ──
    """CREATE TABLE IF NOT EXISTS pipeline_failures (
        id SERIAL PRIMARY KEY, step TEXT, script TEXT,
        stderr_tail TEXT, failed_at TIMESTAMPTZ DEFAULT NOW())""",
    """CREATE TABLE IF NOT EXISTS pipeline_steps (
        id SERIAL PRIMARY KEY, run_date DATE DEFAULT CURRENT_DATE,
        step TEXT, script TEXT, ok BOOLEAN,
        error TEXT, ran_at TIMESTAMPTZ DEFAULT NOW())""",
    """CREATE TABLE IF NOT EXISTS sbi_haiku_run_log (
        id SERIAL PRIMARY KEY, run_date DATE DEFAULT CURRENT_DATE,
        company TEXT, spent_usd NUMERIC(8,4) NOT NULL DEFAULT 0,
        ok BOOLEAN, note TEXT, ran_at TIMESTAMPTZ DEFAULT NOW())""",
    # ── pre-open forward capture (Zerodha has no historical book API) ──
    """CREATE TABLE IF NOT EXISTS ipo_preopen_book (
        id SERIAL PRIMARY KEY, symbol TEXT, discovery_price NUMERIC,
        buy_qty BIGINT, sell_qty BIGINT, lean_pct NUMERIC,
        captured_at TIMESTAMPTZ DEFAULT NOW(), source TEXT DEFAULT 'live')""",
    # ── GUARDRAIL A: natural-key UNIQUE indexes so cleanups can't let dups
    # return (the recurring double-Laser). One canonical row per IPO/tick. ──
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_intel_company ON ipo_intelligence (lower(regexp_replace(company_name,'[^a-zA-Z0-9]','','g')))",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_consol_company ON ipo_consolidated (lower(regexp_replace(company_name,'[^a-zA-Z0-9]','','g')))",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_verdicts_company ON ipo_verdicts (lower(regexp_replace(company_name,'[^a-zA-Z0-9]','','g')))",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_tick_sym_time ON ipo_tick_feed (upper(regexp_replace(symbol,'[^A-Za-z0-9]','','g')), recorded_at)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_level_sym_date ON ipo_level_analysis (upper(regexp_replace(symbol,'[^A-Za-z0-9]','','g')), trade_date)",
    # ── GUARDRAIL C: data source registry (which feed is authoritative per domain) ──
    """CREATE TABLE IF NOT EXISTS data_source_registry (
        domain TEXT PRIMARY KEY, source TEXT NOT NULL, updated_at TIMESTAMPTZ DEFAULT NOW())""",
    "INSERT INTO data_source_registry (domain, source) VALUES ('indices','kite'),('vix','kite'),('pcr','kite'),('fii_dii','kite-or-nse'),('ipo_dates','nse-primary-chittorgarh-fallback'),('quotes','kite') ON CONFLICT (domain) DO NOTHING",
    # ── GUARDRAIL G: RHP spend keyed by PDF content-hash (never re-pay per doc) ──
    "ALTER TABLE ipo_rhp_intel ADD COLUMN IF NOT EXISTS pdf_sha256 TEXT",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_rhp_pdf_sha ON ipo_rhp_intel (pdf_sha256) WHERE pdf_sha256 IS NOT NULL",
    # ── admin job console ──
    """CREATE TABLE IF NOT EXISTS job_runs (
        id BIGSERIAL PRIMARY KEY, job TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'queued', requested_by TEXT,
        requested_at TIMESTAMPTZ DEFAULT now(), started_at TIMESTAMPTZ,
        finished_at TIMESTAMPTZ, exit_code INT, error TEXT, log_tail TEXT)""",
]

def main():
    conn = psycopg2.connect(os.environ["DATABASE_URL"]); cur = conn.cursor()
    for i, ddl in enumerate(DDL, 1):
        cur.execute(ddl)
    conn.commit(); conn.close()
    print(f"schema_sync: {len(DDL)} statements applied (all idempotent)")

if __name__ == "__main__":
    main()
