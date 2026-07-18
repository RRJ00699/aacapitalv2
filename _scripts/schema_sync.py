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

# GUARDRAIL A canon — identical string used by BOTH the dedup DELETE and the
# CREATE UNIQUE INDEX so they can never disagree. Strips company-suffix noise
# (Ltd/Limited/Pvt/Private/India/and), ampersand, and non-alphanumerics (#156).
def _canon(col):
    # ONE canon for BOTH the dedup DELETE and the UNIQUE INDEX (byte-identical,
    # cannot drift). Strips company-suffix noise (ltd|limited|pvt|private|and),
    # ampersand, non-alphanumerics. Deliberately does NOT strip 'india' — that
    # would merge 'India Cements' with 'Cements' and, since this drives a
    # destructive DELETE, wrongly remove a real row (Rakesh's logged edge case,
    # 2026-07-17). No uniqueness contract depends on india-stripping (app joins
    # are fuzzy LEFT JOINs), so dropping it here is strictly safer.
    return (f"regexp_replace(lower({col}), "
            f"'\\y(ltd|limited|pvt|private|and)\\y|&|[^a-z0-9]', '', 'g')")


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
    # ipo_research_notes had NO id column: sbi_haiku_extract selects n.id and threw
    # "column id does not exist" on EVERY run since launch -> 0 attempts, $0 spent,
    # 244 notes untouched (2026-07-18). SERIAL backfills existing rows.
    "ALTER TABLE ipo_research_notes ADD COLUMN IF NOT EXISTS id SERIAL",
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
    # self-heal: drop dup companies (keep lowest ctid) so the unique index applies
    f"""DELETE FROM ipo_intelligence a USING ipo_intelligence b
       WHERE a.ctid > b.ctid AND {_canon('a.company_name')} = {_canon('b.company_name')}""",
    f"CREATE UNIQUE INDEX IF NOT EXISTS ux_intel_company ON ipo_intelligence (({_canon('company_name')}))",
    f"""DELETE FROM ipo_consolidated a USING ipo_consolidated b
       WHERE a.ctid > b.ctid AND {_canon('a.company_name')} = {_canon('b.company_name')}""",
    f"CREATE UNIQUE INDEX IF NOT EXISTS ux_consol_company ON ipo_consolidated (({_canon('company_name')}))",
    f"""DELETE FROM ipo_verdicts a USING ipo_verdicts b
       WHERE a.ctid > b.ctid AND {_canon('a.company_name')} = {_canon('b.company_name')}""",
    f"CREATE UNIQUE INDEX IF NOT EXISTS ux_verdicts_company ON ipo_verdicts (({_canon('company_name')}))",
    # ipo_tick_feed is TIME-SERIES (many rows per symbol) — NO unique constraint:
    # a same-second collision would drop a legitimate tick. A non-unique index
    # supports the canon lookups; writer-side ON CONFLICT is the dedup layer.
    "CREATE INDEX IF NOT EXISTS ix_tick_sym_time ON ipo_tick_feed (upper(regexp_replace(regexp_replace(symbol,'[-_.]?(EQ|BE|BZ|NS)$','','i'),'[^A-Za-z0-9]','','g')), recorded_at)",
    # ipo_level_analysis is one-row-per-symbol-per-day and its writer already
    # ON CONFLICT (symbol, trade_date) DO UPDATE — so a UNIQUE key is correct here.
    """DELETE FROM ipo_level_analysis a USING ipo_level_analysis b
       WHERE a.ctid > b.ctid AND a.symbol = b.symbol AND a.trade_date = b.trade_date""",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_level_sym_date ON ipo_level_analysis (symbol, trade_date)",
    "ALTER TABLE ipo_preopen_book ADD COLUMN IF NOT EXISTS state_hash TEXT",
    "ALTER TABLE ipo_preopen_book ADD COLUMN IF NOT EXISTS ieq BIGINT",
    "ALTER TABLE ipo_preopen_book ADD COLUMN IF NOT EXISTS best_bid NUMERIC",
    "ALTER TABLE ipo_preopen_book ADD COLUMN IF NOT EXISTS best_bid_qty BIGINT",
    "ALTER TABLE ipo_preopen_book ADD COLUMN IF NOT EXISTS best_ask NUMERIC",
    "ALTER TABLE ipo_preopen_book ADD COLUMN IF NOT EXISTS best_ask_qty BIGINT",
    "ALTER TABLE ipo_preopen_book ADD COLUMN IF NOT EXISTS cancelled_qty BIGINT",
    """DELETE FROM ipo_preopen_book a USING ipo_preopen_book b
       WHERE a.ctid > b.ctid AND a.state_hash = b.state_hash AND a.state_hash IS NOT NULL""",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_preopen_state ON ipo_preopen_book(state_hash)",
    """CREATE TABLE IF NOT EXISTS nse_preopen_raw (
        id SERIAL PRIMARY KEY, symbol TEXT, payload JSONB,
        captured_at TIMESTAMPTZ DEFAULT NOW())""",
    f"""DELETE FROM ipo_research_notes a USING ipo_research_notes b
       WHERE a.ctid > b.ctid AND a.source = b.source
         AND {_canon('a.company')} = {_canon('b.company')}""",
    f"CREATE UNIQUE INDEX IF NOT EXISTS ux_notes_company_source ON ipo_research_notes (({_canon('company')}), source)",
    # ── GUARDRAIL C: data source registry (which feed is authoritative per domain) ──
    """CREATE TABLE IF NOT EXISTS data_source_registry (
        domain TEXT PRIMARY KEY, source TEXT NOT NULL, updated_at TIMESTAMPTZ DEFAULT NOW())""",
    "INSERT INTO data_source_registry (domain, source) VALUES ('indices','kite'),('vix','kite'),('pcr','kite'),('fii_dii','kite-or-nse'),('ipo_dates','nse-primary-chittorgarh-fallback'),('quotes','kite') ON CONFLICT (domain) DO NOTHING",
    # ── GUARDRAIL G: RHP spend keyed by PDF content-hash (never re-pay per doc) ──
    "ALTER TABLE ipo_rhp_intel ADD COLUMN IF NOT EXISTS pdf_sha256 TEXT",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_rhp_pdf_sha ON ipo_rhp_intel (pdf_sha256) WHERE pdf_sha256 IS NOT NULL",
    # ── PILLAR 2: DATA LINEAGE — every field's Source -> Parser -> DB provenance,
    # plus freshness. One row per (table, column) declaring where it comes from
    # and how stale it's allowed to be. Populated by lineage_registry.py. ──
    """CREATE TABLE IF NOT EXISTS data_lineage (
        table_name TEXT NOT NULL, column_name TEXT NOT NULL,
        source TEXT NOT NULL,            -- e.g. 'nse-api', 'chittorgarh', 'kite', 'sonnet-rhp', 'derived'
        parser TEXT,                     -- script that produces it
        freshness_sla_hours NUMERIC,     -- null = static/reference
        last_verified TIMESTAMPTZ,
        PRIMARY KEY (table_name, column_name))""",
    # per-run ingestion audit: what ran, how many rows, ok/fail, when
    """CREATE TABLE IF NOT EXISTS ingestion_audit (
        id BIGSERIAL PRIMARY KEY, source TEXT, script TEXT,
        rows_written INT, rows_skipped INT, ok BOOLEAN, note TEXT,
        started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ DEFAULT NOW())""",
    # freshness snapshot: latest write timestamp per source-domain (health monitor reads this)
    """CREATE TABLE IF NOT EXISTS data_freshness (
        domain TEXT PRIMARY KEY, last_write TIMESTAMPTZ,
        row_count BIGINT, updated_at TIMESTAMPTZ DEFAULT NOW())""",
    # ── admin job console ──
    # ── trade journal ──
    # The table EXISTS in prod but is missing the columns sync_trade_journal
    # writes ("SCHEMA MISMATCH — trade_journal lacks ['action','broker',
    # 'broker_order_id','entry_date',...]" on the StepBoard, 2026-07-18).
    # CREATE TABLE IF NOT EXISTS is a NO-OP on an existing table, so the columns
    # must be added individually. broker_order_id is UNIQUE so re-syncing the
    # same Zerodha order is idempotent.
    """CREATE TABLE IF NOT EXISTS trade_journal (
        id BIGSERIAL PRIMARY KEY, created_at TIMESTAMPTZ DEFAULT NOW())""",
    "ALTER TABLE trade_journal ADD COLUMN IF NOT EXISTS broker_order_id TEXT",
    "ALTER TABLE trade_journal ADD COLUMN IF NOT EXISTS symbol TEXT",
    "ALTER TABLE trade_journal ADD COLUMN IF NOT EXISTS exchange TEXT",
    "ALTER TABLE trade_journal ADD COLUMN IF NOT EXISTS action TEXT",
    "ALTER TABLE trade_journal ADD COLUMN IF NOT EXISTS quantity NUMERIC",
    "ALTER TABLE trade_journal ADD COLUMN IF NOT EXISTS price NUMERIC",
    "ALTER TABLE trade_journal ADD COLUMN IF NOT EXISTS broker TEXT",
    "ALTER TABLE trade_journal ADD COLUMN IF NOT EXISTS entry_date DATE",
    "ALTER TABLE trade_journal ADD COLUMN IF NOT EXISTS timestamp TIMESTAMPTZ",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_trade_journal_order ON trade_journal(broker_order_id)",

    # ── NSE pre-open capture (nse_preopen_capture.py) ──
    "ALTER TABLE ipo_preopen_book ADD COLUMN IF NOT EXISTS ieq BIGINT",
    "ALTER TABLE ipo_preopen_book ADD COLUMN IF NOT EXISTS best_bid NUMERIC",
    "ALTER TABLE ipo_preopen_book ADD COLUMN IF NOT EXISTS best_bid_qty BIGINT",
    "ALTER TABLE ipo_preopen_book ADD COLUMN IF NOT EXISTS best_ask NUMERIC",
    "ALTER TABLE ipo_preopen_book ADD COLUMN IF NOT EXISTS best_ask_qty BIGINT",
    "ALTER TABLE ipo_preopen_book ADD COLUMN IF NOT EXISTS cancelled_qty BIGINT",
    "ALTER TABLE ipo_preopen_book ADD COLUMN IF NOT EXISTS state_hash TEXT",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_preopen_state ON ipo_preopen_book(state_hash)",
    """CREATE TABLE IF NOT EXISTS nse_preopen_raw (
        id SERIAL PRIMARY KEY, symbol TEXT, payload JSONB,
        captured_at TIMESTAMPTZ DEFAULT NOW())""",
    """CREATE TABLE IF NOT EXISTS job_runs (
        id BIGSERIAL PRIMARY KEY, job TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'queued', requested_by TEXT,
        requested_at TIMESTAMPTZ DEFAULT now(), started_at TIMESTAMPTZ,
        finished_at TIMESTAMPTZ, exit_code INT, error TEXT, log_tail TEXT)""",
]

def main():
    # PER-STATEMENT ISOLATION (Rakesh 2026-07-17): each DDL commits on its own so
    # ONE failure (e.g. a UNIQUE index blocked by existing dupes) can never roll
    # back the other statements. Failures are reported, not fatal; the run exits
    # non-zero if any failed so the StepBoard shows red, but everything that CAN
    # apply DOES apply.
    conn = psycopg2.connect(os.environ["DATABASE_URL"]); conn.autocommit = True
    cur = conn.cursor()
    ok = 0; failed = []
    for ddl in DDL:
        try:
            cur.execute(ddl); ok += 1
        except Exception as e:
            label = " ".join(ddl.split()[:6])
            failed.append((label, str(e).splitlines()[0][:160]))
    conn.close()
    print(f"schema_sync: {ok}/{len(DDL)} applied"
          + (f" · {len(failed)} FAILED (isolated, others still applied):" if failed else " (all idempotent)"))
    for label, err in failed:
        print(f"  ✗ {label} … — {err}")
    if failed:
        # A blocked UNIQUE index almost always means real duplicates to clean.
        import sys; sys.exit(1)

if __name__ == "__main__":
    main()
