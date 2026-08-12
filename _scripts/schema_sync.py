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
    # nse_issue_info (2026-07-23): raw NSE issue-information API payloads —
    # anchor evidence landing zone (owner URL pattern). Durable; fill-empty.
    """CREATE TABLE IF NOT EXISTS nse_issue_info (
        symbol TEXT PRIMARY KEY, raw_json JSONB,
        anchor_portion_shares BIGINT, fetched_at TIMESTAMPTZ)""",
    # rule_validation_results (Phase 10, 2026-07-22): every backtest result
    # with full provenance — dataset, filters, versions, timestamp. Durable.
    """CREATE TABLE IF NOT EXISTS rule_validation_results (
        id BIGSERIAL PRIMARY KEY,
        rule_id TEXT NOT NULL, rule_version TEXT NOT NULL,
        backtest_version TEXT NOT NULL, dataset TEXT NOT NULL,
        sql_filter TEXT NOT NULL, rule_filter TEXT NOT NULL,
        date_range TEXT, n INT NOT NULL,
        win_rate NUMERIC, avg_return NUMERIC, median_return NUMERIC,
        max_drawdown NUMERIC, expectancy NUMERIC, p_vs_baseline NUMERIC,
        beats_baseline BOOLEAN, baseline_win_rate NUMERIC, universe_n INT,
        run_at TIMESTAMPTZ NOT NULL)""",
    # symbol_aliases (2026-07-22): NSE renames/mergers for historical backfills
    # (e.g. ZOMATO -> ETERNAL). Owner-curated; backfill scripts consult it.
    """CREATE TABLE IF NOT EXISTS symbol_aliases (
        old_symbol TEXT PRIMARY KEY,
        new_symbol TEXT NOT NULL,
        note TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW())""",
    # ── ipo_news (2026-07-22): one selected street article per IPO. Discovery
    # via whitelisted Google News RSS (free) + manual admin override. Metadata
    # + short snippet ONLY — never full article text (copyright + licensing).
    """CREATE TABLE IF NOT EXISTS ipo_news (
        id BIGSERIAL PRIMARY KEY,
        company_name TEXT NOT NULL,
        nse_symbol TEXT,
        publisher TEXT NOT NULL,
        headline TEXT NOT NULL,
        url TEXT NOT NULL,
        published_at TIMESTAMPTZ,
        snippet TEXT,
        selection_score INT,
        source TEXT NOT NULL DEFAULT 'rss',
        fetch_status TEXT NOT NULL DEFAULT 'ok',
        is_current BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMPTZ DEFAULT NOW())""",
    # ── ipo_intelligence: derived/score/quality columns ──
    # 2026-07-21: eligibility columns — production has them from the scraper
    # era, but the DDL owner never declared them; a fresh DB crashed the
    # Haiku spend-gate (caught by test_sbi_haiku_finds_work).

    # ── GOLDEN TABLE (owner decision 2026-07-22): every field the UI +
    # backtests read, in ONE readable object. ipo_consolidated is REBUILT
    # each pipeline run (see test_no_columns_on_rebuilt_tables — the wiped
    # listing-tape incident), so durable fields live in ipo_golden (its OWN
    # table, keyed by normalized company name) and the VIEW ipo_master joins
    # them: single-object reads, rebuild-proof storage. Named ipo_gold because
    # ipo_master already exists in prod as a LEGACY v1 table with dependents
    # (foundation engines) — never hijack a live name.
    """CREATE TABLE IF NOT EXISTS ipo_golden (
        company_key TEXT PRIMARY KEY,
        company_name TEXT NOT NULL,
        nse_symbol TEXT,
        isin TEXT, lot_size INT, face_value NUMERIC,
        allotment_date DATE, refund_date DATE, credit_date DATE,
        anchor_amount_cr NUMERIC, anchor_lock30_date DATE, anchor_lock90_date DATE,
        sub_day1_x NUMERIC, sub_day2_x NUMERIC, sub_day3_x NUMERIC,
        bnii_x NUMERIC, snii_x NUMERIC, total_applications BIGINT,
        employee_discount NUMERIC, employee_quota_shares BIGINT, shareholder_quota_shares BIGINT,
        promoter_pre_pct NUMERIC, promoter_post_pct NUMERIC,
        mcap_cr NUMERIC, issue_expenses_cr NUMERIC,
        registrar_name TEXT, registrar_phone TEXT, registrar_email TEXT,
        ronw NUMERIC, ebitda_margin NUMERIC, price_to_book NUMERIC,
        gmp_history_json JSONB, financials_3y_json JSONB,
        rhp_sonnet_json JSONB, sbi_haiku_json JSONB,
        street_headline TEXT, street_publisher TEXT, street_url TEXT,
        candles_json JSONB,
        final_qib NUMERIC, final_nii NUMERIC, final_retail NUMERIC, final_total NUMERIC,
        industry TEXT, nse_listing_date DATE,
        golden_filled_at TIMESTAMPTZ)""",
    # ipo_golden is DURABLE and already exists in prod - new fields must be
    # ALTERs; putting them only inside CREATE IF NOT EXISTS no-ops forever
    # (owner receipts 2026-07-22: 87/87 applied, zero columns created).
    "ALTER TABLE ipo_golden ADD COLUMN IF NOT EXISTS final_qib NUMERIC",
    "ALTER TABLE ipo_golden ADD COLUMN IF NOT EXISTS final_nii NUMERIC",
    "ALTER TABLE ipo_golden ADD COLUMN IF NOT EXISTS final_retail NUMERIC",
    "ALTER TABLE ipo_golden ADD COLUMN IF NOT EXISTS final_total NUMERIC",
    "ALTER TABLE ipo_golden ADD COLUMN IF NOT EXISTS industry TEXT",
    "ALTER TABLE ipo_golden ADD COLUMN IF NOT EXISTS nse_listing_date DATE",
    "__IPO_GOLD_VIEW__",  # generated dynamically — see build_ipo_gold_view()
    "ALTER TABLE ipo_intelligence ADD COLUMN IF NOT EXISTS is_sme BOOLEAN",
    "ALTER TABLE ipo_intelligence ADD COLUMN IF NOT EXISTS issue_size_cr NUMERIC",
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
    # ── PR-A provenance (PROVENANCE_DESIGN.md §2 — additive only) ──
    """CREATE TABLE IF NOT EXISTS ipo_insights (
        insight_id BIGSERIAL PRIMARY KEY,
        ipo_id INT NOT NULL,
        category TEXT NOT NULL,
        statement TEXT NOT NULL,
        direction TEXT NOT NULL CHECK (direction IN ('positive','negative','neutral','incomplete')),
        source_type TEXT NOT NULL,
        source_name TEXT, source_document_id TEXT, source_url TEXT,
        source_locator TEXT, source_excerpt TEXT,
        extraction_model TEXT, analysis_model TEXT, analysis_run_id TEXT,
        confidence TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        source_published_at TIMESTAMPTZ, source_downloaded_at TIMESTAMPTZ,
        is_current BOOLEAN DEFAULT TRUE)""",
    "CREATE INDEX IF NOT EXISTS idx_ipo_insights_ipo ON ipo_insights (ipo_id) WHERE is_current",
    """CREATE TABLE IF NOT EXISTS ipo_stage_state (
        ipo_id INT NOT NULL, stage TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('CONFIRMED','PARTIAL','PENDING','FAILED')),
        attempt_count INT DEFAULT 0,
        started_at TIMESTAMPTZ, completed_at TIMESTAMPTZ,
        last_error TEXT, next_retry_at TIMESTAMPTZ,
        input_fingerprint TEXT, output_fingerprint TEXT, pipeline_version TEXT,
        PRIMARY KEY (ipo_id, stage))""",
    # stale-verdict detection (baseline 2026-07-21: verdicts existed with no
    # document behind them) — fingerprint column; ADD IF NOT EXISTS is a no-op
    # where prod already has it (contract_schema.py lists it).
    "ALTER TABLE ipo_rhp_intel ADD COLUMN IF NOT EXISTS pdf_sha256 TEXT",
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
    # CREATE TABLE IF NOT EXISTS is a NO-OP on a pre-existing table, so an older
    # ipo_preopen_book never gained these columns — `source` was missing entirely
    # (2026-07-19). Same class of bug as trade_journal. Add each individually so
    # an existing table is repaired rather than skipped.
    "ALTER TABLE ipo_preopen_book ADD COLUMN IF NOT EXISTS symbol TEXT",
    "ALTER TABLE ipo_preopen_book ADD COLUMN IF NOT EXISTS discovery_price NUMERIC",
    "ALTER TABLE ipo_preopen_book ADD COLUMN IF NOT EXISTS buy_qty BIGINT",
    "ALTER TABLE ipo_preopen_book ADD COLUMN IF NOT EXISTS sell_qty BIGINT",
    "ALTER TABLE ipo_preopen_book ADD COLUMN IF NOT EXISTS lean_pct NUMERIC",
    "ALTER TABLE ipo_preopen_book ADD COLUMN IF NOT EXISTS captured_at TIMESTAMPTZ DEFAULT NOW()",
    "ALTER TABLE ipo_preopen_book ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'live'",
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
    # The table EXISTS in prod but lacks the columns sync_trade_journal writes
    # ("SCHEMA MISMATCH — trade_journal lacks ['action','broker',
    # 'broker_order_id','entry_date',...]" on the StepBoard, 2026-07-18).
    # CREATE TABLE IF NOT EXISTS is a NO-OP on an existing table, so each column
    # must be added individually. broker_order_id UNIQUE makes re-syncing the
    # same Zerodha order idempotent.
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
    # Phase-5 fix (baseline 2026-07-21): compute_journal_outcomes writes these
    # three but NOTHING owned their DDL — the thesis UPDATE threw UndefinedColumn
    # on every nightly ("compute journal outcomes" in pipeline_failures 2x/day).
    "ALTER TABLE trade_journal ADD COLUMN IF NOT EXISTS pnl_pct NUMERIC",
    "ALTER TABLE trade_journal ADD COLUMN IF NOT EXISTS outcome TEXT",
    "ALTER TABLE trade_journal ADD COLUMN IF NOT EXISTS thesis TEXT",
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
    """CREATE TABLE IF NOT EXISTS access_requests (
        email TEXT PRIMARY KEY, name TEXT, status TEXT NOT NULL DEFAULT 'pending',
        requested_at TIMESTAMPTZ DEFAULT now(), decided_at TIMESTAMPTZ,
        decided_by TEXT, note TEXT)""",
    "ALTER TABLE access_requests ADD COLUMN IF NOT EXISTS note TEXT",
]



# Golden-only columns (must mirror the ipo_golden CREATE above, minus keys).
GOLD_COLS = ["isin", "lot_size", "face_value", "allotment_date", "refund_date",
    "final_qib", "final_nii", "final_retail", "final_total", "industry", "nse_listing_date",
    "credit_date", "anchor_amount_cr", "anchor_lock30_date", "anchor_lock90_date",
    "sub_day1_x", "sub_day2_x", "sub_day3_x", "bnii_x", "snii_x",
    "total_applications", "employee_discount", "employee_quota_shares",
    "shareholder_quota_shares", "promoter_pre_pct", "promoter_post_pct",
    "mcap_cr", "issue_expenses_cr", "registrar_name", "registrar_phone",
    "registrar_email", "ronw", "ebitda_margin", "price_to_book",
    "gmp_history_json", "financials_3y_json", "rhp_sonnet_json",
    "sbi_haiku_json", "street_headline", "street_publisher", "street_url",
    "candles_json", "golden_filled_at"]


def build_ipo_gold_view(cur):
    """ipo_consolidated is REBUILT per run and its column set can change
    (prod already carries e.g. isin), so the one-object view is GENERATED
    from information_schema each sync: overlapping names become
    COALESCE(consolidated, golden); golden-only columns come from g."""
    cur.execute("""SELECT column_name FROM information_schema.columns
                   WHERE table_name = 'ipo_consolidated' ORDER BY ordinal_position""")
    cons = [r[0] for r in cur.fetchall()]
    cur.execute("""SELECT column_name FROM information_schema.columns
                   WHERE table_name = 'ipo_golden'""")
    gold_actual = {r[0] for r in cur.fetchall()}
    gold = [c for c in GOLD_COLS if c in gold_actual]  # only columns that exist
    gold_only = [c for c in gold if c not in cons]
    sel = []
    for c in cons:
        if c in gold:
            sel.append(f'COALESCE(c."{c}", g."{c}") AS "{c}"')
        else:
            sel.append(f'c."{c}"')
    sel += [f'g."{c}"' for c in gold_only]
    return ("CREATE OR REPLACE VIEW ipo_gold AS SELECT " + ", ".join(sel) +
            " FROM ipo_consolidated c LEFT JOIN ipo_golden g ON g.company_key = "
            "regexp_replace(lower(c.company_name),'(ltd|limited|and|&)|[^a-z0-9]','','g')")


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
            if ddl == "__IPO_GOLD_VIEW__":
                # view shape changes need DROP first (CREATE OR REPLACE can't
                # reorder/remove columns). DROP+CREATE run in ONE explicit
                # transaction so readers never observe a missing view, even
                # mid-sync under traffic (autocommit would commit each alone).
                cur.execute("BEGIN")
                try:
                    cur.execute("DROP VIEW IF EXISTS ipo_gold")
                    cur.execute(build_ipo_gold_view(cur))
                    cur.execute("COMMIT")
                except Exception:
                    cur.execute("ROLLBACK"); raise
                ok += 1
                continue
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
