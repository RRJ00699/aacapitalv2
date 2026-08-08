-- _scripts/migrations/20260617_prod_ready_tables.sql
-- Production-ready schema for AACapital V2.
-- Created: June 17, 2026
-- All statements are idempotent (CREATE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS).
-- Safe to re-run at any time.

-- ═══════════════════════════════════════════════════════════════════
-- 1. PLATFORM CONFIG (key-value store for tokens, settings)
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS platform_config (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO platform_config (key, value) VALUES ('kite_access_token', 'not_set_yet')
    ON CONFLICT (key) DO NOTHING;

-- ═══════════════════════════════════════════════════════════════════
-- 2. COMPANY MASTER (universe of tracked stocks)
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS company_master (
    id             SERIAL PRIMARY KEY,
    symbol         TEXT UNIQUE NOT NULL,
    nse_symbol     TEXT,
    company_name   TEXT,
    sector         TEXT,
    industry       TEXT,
    industry_group TEXT,
    market_cap     NUMERIC,
    is_active      BOOLEAN DEFAULT TRUE,
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    updated_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_company_master_symbol ON company_master (symbol);
CREATE INDEX IF NOT EXISTS idx_company_master_sector ON company_master (sector);

-- ═══════════════════════════════════════════════════════════════════
-- 3. TECHNICAL SIGNALS (computed by generate_signals.py daily)
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS technical_signals (
    id                   SERIAL PRIMARY KEY,
    symbol               TEXT        NOT NULL,
    signal_date          DATE,
    timeframe            TEXT        DEFAULT 'daily',
    close                NUMERIC(12,4),
    change_pct           NUMERIC(8,4),
    volume               BIGINT,
    avg_volume_20        NUMERIC,

    -- EMA fields
    ema200               NUMERIC(12,4),
    ema50                NUMERIC(12,4),
    above_ema200         BOOLEAN     DEFAULT FALSE,
    price_above_ema30    BOOLEAN     DEFAULT FALSE,

    -- Score fields
    buy_zone_score       NUMERIC(5,2),
    mb_score             INTEGER,
    convergence_score    NUMERIC(5,2),
    probability_score    NUMERIC(5,2),
    breakout_watch_score INTEGER,
    breakout_watch_tier  TEXT,

    -- Pattern flags
    is_nr7               BOOLEAN     DEFAULT FALSE,
    nr7                  BOOLEAN     DEFAULT FALSE,
    vr7                  BOOLEAN     DEFAULT FALSE,
    volume_expansion     BOOLEAN     DEFAULT FALSE,
    ema_crossover        BOOLEAN     DEFAULT FALSE,
    all_criteria_met     BOOLEAN     DEFAULT FALSE,

    -- Momentum
    momentum_6m          NUMERIC(8,4),
    momentum_3m          NUMERIC(8,4),

    -- Volume analysis
    vol_compression      NUMERIC(8,4),
    volume_ratio_20      NUMERIC(8,4),

    -- Stage analysis
    stage                TEXT,
    stage_label          TEXT,
    base_months          INTEGER,

    -- 52-week high proximity
    pct_below_high       NUMERIC(8,4),

    -- Signal classification
    signal_strength      TEXT,
    action_label         TEXT,
    conviction           TEXT,

    -- RSI
    rsi                  NUMERIC(5,2),

    updated_at           TIMESTAMPTZ DEFAULT NOW(),
    synced_at            TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (symbol, timeframe)
);

CREATE INDEX IF NOT EXISTS idx_ts_symbol     ON technical_signals (symbol);
CREATE INDEX IF NOT EXISTS idx_ts_mb_score   ON technical_signals (mb_score DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_ts_bw_score   ON technical_signals (breakout_watch_score DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_ts_timeframe  ON technical_signals (timeframe);
CREATE INDEX IF NOT EXISTS idx_ts_signal_date ON technical_signals (signal_date DESC);

-- ═══════════════════════════════════════════════════════════════════
-- 4. PRICE CANDLES (daily OHLCV — main candle store)
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS price_candles (
    id       BIGSERIAL PRIMARY KEY,
    symbol   TEXT    NOT NULL,
    date     DATE    NOT NULL,
    open     NUMERIC(12,4),
    high     NUMERIC(12,4),
    low      NUMERIC(12,4),
    close    NUMERIC(12,4),
    volume   BIGINT,
    UNIQUE (symbol, date)
);

CREATE INDEX IF NOT EXISTS idx_pc_symbol_date ON price_candles (symbol, date DESC);

-- ═══════════════════════════════════════════════════════════════════
-- 5. IPO INTELLIGENCE
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS ipo_intelligence (
    id                       SERIAL PRIMARY KEY,
    company_name             TEXT        NOT NULL,
    nse_symbol               TEXT,
    issue_price              NUMERIC(10,2),
    issue_size_cr            NUMERIC(12,2),
    open_date                DATE,
    close_date               DATE,
    listing_date             DATE,
    listing_price            NUMERIC(10,2),
    listing_day_close        NUMERIC(10,2),
    gmp_percentage           NUMERIC(8,2),
    brlm_name                TEXT,
    brlm_score               INTEGER,
    sector                   TEXT,
    ofs_pct                  NUMERIC(6,2),
    fresh_issue_pct          NUMERIC(6,2),
    qib_subscription_x       NUMERIC(10,2),
    nii_subscription_x       NUMERIC(10,2),
    rii_subscription_x       NUMERIC(10,2),
    total_subscription_x     NUMERIC(10,2),
    anchor_tier1_count       INTEGER,
    anchor_allotment_date    DATE,
    listing_gain_pct         NUMERIC(8,2),
    open_gain_pct            NUMERIC(8,2),
    play_label               TEXT,
    play_reasoning           TEXT,
    status                   TEXT        DEFAULT 'UPCOMING',
    score                    INTEGER,
    created_at               TIMESTAMPTZ DEFAULT NOW(),
    updated_at               TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ipo_close_date ON ipo_intelligence (close_date DESC);
CREATE INDEX IF NOT EXISTS idx_ipo_listing_date ON ipo_intelligence (listing_date DESC);
CREATE INDEX IF NOT EXISTS idx_ipo_status ON ipo_intelligence (status);

-- ═══════════════════════════════════════════════════════════════════
-- 6. BRLM SCORES
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS brlm_scores (
    id              SERIAL PRIMARY KEY,
    brlm_name       TEXT        UNIQUE NOT NULL,
    score           INTEGER,
    tier            TEXT,
    total_ipos      INTEGER     DEFAULT 0,
    avg_listing_gain NUMERIC(8,2),
    calculated_at   TIMESTAMPTZ DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════════
-- 7. SHAREHOLDING HISTORY
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS shareholding_history (
    id           SERIAL PRIMARY KEY,
    nse_symbol   TEXT        NOT NULL,
    quarter      TEXT        NOT NULL,
    promoter_pct NUMERIC(6,2),
    fii_pct      NUMERIC(6,2),
    dii_pct      NUMERIC(6,2),
    mf_pct       NUMERIC(6,2),
    pledged_pct  NUMERIC(6,2),
    public_pct   NUMERIC(6,2),
    scraped_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (nse_symbol, quarter)
);

CREATE INDEX IF NOT EXISTS idx_sh_symbol  ON shareholding_history (nse_symbol);
CREATE INDEX IF NOT EXISTS idx_sh_quarter ON shareholding_history (quarter);

-- ═══════════════════════════════════════════════════════════════════
-- 8. MANAGEMENT COMMENTARY (see management_commentary_schema.sql
--    for full definition — this is the minimal prod-ready version)
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS management_commentary (
    id                 SERIAL PRIMARY KEY,
    nse_symbol         TEXT        NOT NULL,
    company_name       TEXT,
    quarter            TEXT        NOT NULL,
    revenue_guidance   TEXT,
    margin_guidance    TEXT,
    order_book_cr      NUMERIC,
    management_tone    TEXT        DEFAULT 'NEUTRAL',
    guidance_direction TEXT        DEFAULT 'NOT_PROVIDED',
    key_growth_drivers JSONB       DEFAULT '[]',
    key_risks          JSONB       DEFAULT '[]',
    positive_surprises JSONB       DEFAULT '[]',
    negative_surprises JSONB       DEFAULT '[]',
    mgmt_quality_score NUMERIC(5,2),
    sentiment_score    NUMERIC(5,2),
    data_source        TEXT        DEFAULT 'SCREENER',
    confidence         TEXT        DEFAULT 'LOW',
    extraction_notes   TEXT,
    created_at         TIMESTAMPTZ DEFAULT NOW(),
    updated_at         TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (nse_symbol, quarter)
);

CREATE INDEX IF NOT EXISTS idx_mc_symbol  ON management_commentary (nse_symbol);
CREATE INDEX IF NOT EXISTS idx_mc_quarter ON management_commentary (quarter);

-- ═══════════════════════════════════════════════════════════════════
-- 9. QUARTERLY RESULTS (earnings data)
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS quarterly_results (
    id                 SERIAL PRIMARY KEY,
    symbol             TEXT        NOT NULL,
    company_name       TEXT,
    fiscal_year        TEXT,
    fiscal_quarter     TEXT        NOT NULL,
    revenue            NUMERIC(16,2),
    revenue_yoy_pct    NUMERIC(8,2),
    pat                NUMERIC(16,2),
    pat_yoy_pct        NUMERIC(8,2),
    ebitda             NUMERIC(16,2),
    ebitda_margin_pct  NUMERIC(6,2),
    eps                NUMERIC(10,4),
    data_source        TEXT,
    created_at         TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (symbol, fiscal_year, fiscal_quarter)
);

-- ═══════════════════════════════════════════════════════════════════
-- 10. EARNINGS ACCELERATION SCORES
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS earnings_acceleration_scores (
    id                         SERIAL PRIMARY KEY,
    symbol                     TEXT        NOT NULL,
    company_name               TEXT,
    fiscal_year                TEXT,
    fiscal_quarter             TEXT        NOT NULL,
    revenue_acceleration_score NUMERIC(5,2) DEFAULT 0,
    pat_acceleration_score     NUMERIC(5,2) DEFAULT 0,
    margin_expansion_score     NUMERIC(5,2) DEFAULT 0,
    consistency_score          NUMERIC(5,2) DEFAULT 0,
    total_score                NUMERIC(5,2) DEFAULT 0,
    acceleration_status        TEXT,
    score_details              JSONB        DEFAULT '{}',
    updated_at                 TIMESTAMPTZ  DEFAULT NOW(),
    UNIQUE (symbol, fiscal_year, fiscal_quarter)
);

-- ═══════════════════════════════════════════════════════════════════
-- 11. AMFI DATA (mutual fund flows)
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS amfi_category_flows (
    id             SERIAL PRIMARY KEY,
    report_year    INTEGER     NOT NULL,
    report_month   INTEGER     NOT NULL,
    category       TEXT        NOT NULL,
    net_inflow_cr  NUMERIC(16,2),
    gross_purchase NUMERIC(16,2),
    gross_redemp   NUMERIC(16,2),
    aum_cr         NUMERIC(16,2),
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (report_year, report_month, category)
);

CREATE TABLE IF NOT EXISTS amfi_commentary_scores (
    id                  SERIAL PRIMARY KEY,
    report_month        INTEGER     NOT NULL,
    report_year         INTEGER     NOT NULL,
    equity_flow_score   NUMERIC(5,2) DEFAULT 0,
    sip_strength_score  NUMERIC(5,2) DEFAULT 0,
    smallcap_heat_score NUMERIC(5,2) DEFAULT 0,
    midcap_heat_score   NUMERIC(5,2) DEFAULT 0,
    debt_shift_score    NUMERIC(5,2) DEFAULT 0,
    liquidity_score     NUMERIC(5,2) DEFAULT 0,
    total_score         NUMERIC(5,2) DEFAULT 0,
    liquidity_status    TEXT,
    score_reason        TEXT,
    score_details       JSONB        DEFAULT '{}',
    updated_at          TIMESTAMPTZ  DEFAULT NOW(),
    UNIQUE (report_month, report_year)
);

-- ═══════════════════════════════════════════════════════════════════
-- 12. MARKET INFRASTRUCTURE
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS market_regimes (
    id                 SERIAL PRIMARY KEY,
    evaluation_date    DATE        UNIQUE,
    regime             TEXT,
    regime_score       NUMERIC(5,2),
    nifty_vs_ema200    TEXT,
    breadth_score      NUMERIC(5,2),
    vix_regime         TEXT,
    fii_trend          TEXT,
    notes              TEXT,
    created_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS market_snapshot (
    id           SERIAL PRIMARY KEY,
    symbol       TEXT,
    last_price   NUMERIC(12,4),
    change_pct   NUMERIC(8,4),
    volume       BIGINT,
    last_updated TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS daily_institutional_flows (
    id         SERIAL PRIMARY KEY,
    date       DATE,
    flow_date  DATE,
    fii_net_cr NUMERIC(16,2),
    dii_net_cr NUMERIC(16,2),
    category   TEXT,
    source     TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS intelligence_jobs (
    id          SERIAL PRIMARY KEY,
    job_type    TEXT,
    status      TEXT        DEFAULT 'pending',
    result      JSONB,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- ═══════════════════════════════════════════════════════════════════
-- 13. STOCK FUNDAMENTALS (used by score_management_commentary.py)
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS stock_fundamentals (
    id             SERIAL PRIMARY KEY,
    nse_symbol     TEXT        UNIQUE NOT NULL,
    name           TEXT,
    sector         TEXT,
    industry       TEXT,
    industry_group TEXT,
    market_cap_cr  NUMERIC(16,2),
    pe_ratio       NUMERIC(10,4),
    pb_ratio       NUMERIC(10,4),
    roe_pct        NUMERIC(8,2),
    debt_equity    NUMERIC(8,4),
    updated_at     TIMESTAMPTZ DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════════
-- 14. MF STOCK SUMMARY (AMFI mutual fund holdings per stock)
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS mf_stock_summary (
    id             SERIAL PRIMARY KEY,
    nse_symbol     TEXT        NOT NULL,
    report_month   TEXT        NOT NULL,
    total_aum_cr   NUMERIC(16,2),
    num_funds      INTEGER,
    avg_weight_pct NUMERIC(8,4),
    trend          TEXT,
    updated_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (nse_symbol, report_month)
);

-- ═══════════════════════════════════════════════════════════════════
-- 15. MANAGEMENT COMMENTARY SCORES & NORMALIZED
--     (matching management_commentary_schema.sql)
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS management_commentary_scores (
    id                  SERIAL PRIMARY KEY,
    symbol              TEXT        NOT NULL,
    company_name        TEXT,
    fiscal_year         TEXT,
    fiscal_quarter      TEXT        NOT NULL,
    demand_score        NUMERIC(5,2) DEFAULT 0,
    margin_score        NUMERIC(5,2) DEFAULT 0,
    order_book_score    NUMERIC(5,2) DEFAULT 0,
    guidance_score      NUMERIC(5,2) DEFAULT 0,
    risk_score          NUMERIC(5,2) DEFAULT 0,
    confidence_score    NUMERIC(5,2) DEFAULT 0,
    total_score         NUMERIC(5,2) DEFAULT 0,
    commentary_status   TEXT,
    score_reason        TEXT,
    score_details       JSONB        DEFAULT '{}',
    updated_at          TIMESTAMPTZ  DEFAULT NOW(),
    UNIQUE (symbol, fiscal_year, fiscal_quarter)
);

CREATE TABLE IF NOT EXISTS management_commentary_normalized (
    id             SERIAL PRIMARY KEY,
    symbol         TEXT        NOT NULL,
    company_name   TEXT,
    fiscal_quarter TEXT        NOT NULL,
    fiscal_year    TEXT,
    management_tone        TEXT,
    guidance_direction     TEXT,
    revenue_guidance       TEXT,
    margin_guidance        TEXT,
    mgmt_quality_score     NUMERIC(5,2),
    sentiment_score        NUMERIC(5,2),
    key_growth_drivers     JSONB DEFAULT '[]',
    key_risks              JSONB DEFAULT '[]',
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    updated_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (symbol, fiscal_quarter)
);
