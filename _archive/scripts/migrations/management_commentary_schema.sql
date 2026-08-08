-- _scripts/migrations/management_commentary_schema.sql
-- Management commentary tables.
-- Read and executed by .github/workflows/management-commentary.yml on every run.
-- All statements use IF NOT EXISTS so re-running is safe (idempotent).

-- ── 1. Primary commentary table (written by score_management_commentary.py) ──
CREATE TABLE IF NOT EXISTS management_commentary (
    id                 SERIAL PRIMARY KEY,
    nse_symbol         TEXT        NOT NULL,
    company_name       TEXT,
    quarter            TEXT        NOT NULL,   -- e.g. "Q4FY25"

    -- Guidance fields
    revenue_guidance   TEXT,
    margin_guidance    TEXT,
    order_book_cr      NUMERIC,

    -- Tone / direction
    management_tone    TEXT        DEFAULT 'NEUTRAL',
        -- BULLISH | CAUTIOUSLY_OPTIMISTIC | NEUTRAL | CAUTIOUS | BEARISH
    guidance_direction TEXT        DEFAULT 'NOT_PROVIDED',
        -- RAISING | STABLE | NOT_PROVIDED | LOWERING

    -- Detail arrays (stored as JSON strings)
    key_growth_drivers JSONB       DEFAULT '[]',
    key_risks          JSONB       DEFAULT '[]',
    positive_surprises JSONB       DEFAULT '[]',
    negative_surprises JSONB       DEFAULT '[]',

    -- Scores
    mgmt_quality_score NUMERIC(5,2),
    sentiment_score    NUMERIC(5,2),

    -- Source metadata
    data_source        TEXT        DEFAULT 'SCREENER',
    confidence         TEXT        DEFAULT 'LOW',
    extraction_notes   TEXT,

    created_at         TIMESTAMPTZ DEFAULT NOW(),
    updated_at         TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (nse_symbol, quarter)
);

CREATE INDEX IF NOT EXISTS idx_mgmt_commentary_symbol  ON management_commentary (nse_symbol);
CREATE INDEX IF NOT EXISTS idx_mgmt_commentary_quarter ON management_commentary (quarter);
CREATE INDEX IF NOT EXISTS idx_mgmt_commentary_tone    ON management_commentary (management_tone);

-- ── 2. Scored commentary table (written by run-intelligence-scoring.ts) ───────
CREATE TABLE IF NOT EXISTS management_commentary_scores (
    id                  SERIAL PRIMARY KEY,
    symbol              TEXT        NOT NULL,
    company_name        TEXT,
    fiscal_year         TEXT,
    fiscal_quarter      TEXT        NOT NULL,

    -- Component scores (0-100)
    demand_score        NUMERIC(5,2) DEFAULT 0,
    margin_score        NUMERIC(5,2) DEFAULT 0,
    order_book_score    NUMERIC(5,2) DEFAULT 0,
    guidance_score      NUMERIC(5,2) DEFAULT 0,
    risk_score          NUMERIC(5,2) DEFAULT 0,
    confidence_score    NUMERIC(5,2) DEFAULT 0,

    -- Aggregate
    total_score         NUMERIC(5,2) DEFAULT 0,
    commentary_status   TEXT,
        -- BULLISH | CAUTIOUSLY_OPTIMISTIC | NEUTRAL | CAUTIOUS | BEARISH
    score_reason        TEXT,
    score_details       JSONB        DEFAULT '{}',

    updated_at          TIMESTAMPTZ  DEFAULT NOW(),

    UNIQUE (symbol, fiscal_year, fiscal_quarter)
);

CREATE INDEX IF NOT EXISTS idx_mc_scores_symbol ON management_commentary_scores (symbol);

-- ── 3. Normalized commentary view (read by run-intelligence-scoring.ts) ───────
-- Bridges the two tables: management_commentary (raw) → management_commentary_scores (scored).
-- scoreManagementCommentary() in lib/intelligence/commentary-score.ts reads this.
CREATE TABLE IF NOT EXISTS management_commentary_normalized (
    id             SERIAL PRIMARY KEY,
    symbol         TEXT        NOT NULL,   -- maps to nse_symbol
    company_name   TEXT,
    fiscal_quarter TEXT        NOT NULL,   -- e.g. "Q4FY25"
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

CREATE INDEX IF NOT EXISTS idx_mc_normalized_symbol ON management_commentary_normalized (symbol);

-- ── 4. Auto-sync trigger: keep management_commentary_normalized in sync ────────
-- When a row is upserted into management_commentary, mirror it to _normalized.
CREATE OR REPLACE FUNCTION sync_commentary_to_normalized()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    fy TEXT;
BEGIN
    -- Derive fiscal_year from quarter string (e.g. "Q4FY25" → "FY25")
    fy := SUBSTRING(NEW.quarter FROM 'FY\d+');

    INSERT INTO management_commentary_normalized (
        symbol, company_name, fiscal_quarter, fiscal_year,
        management_tone, guidance_direction, revenue_guidance, margin_guidance,
        mgmt_quality_score, sentiment_score, key_growth_drivers, key_risks,
        updated_at
    ) VALUES (
        NEW.nse_symbol, NEW.company_name, NEW.quarter, fy,
        NEW.management_tone, NEW.guidance_direction,
        NEW.revenue_guidance, NEW.margin_guidance,
        NEW.mgmt_quality_score, NEW.sentiment_score,
        COALESCE(NEW.key_growth_drivers, '[]'),
        COALESCE(NEW.key_risks, '[]'),
        NOW()
    )
    ON CONFLICT (symbol, fiscal_quarter) DO UPDATE SET
        company_name       = EXCLUDED.company_name,
        management_tone    = EXCLUDED.management_tone,
        guidance_direction = EXCLUDED.guidance_direction,
        revenue_guidance   = EXCLUDED.revenue_guidance,
        margin_guidance    = EXCLUDED.margin_guidance,
        mgmt_quality_score = EXCLUDED.mgmt_quality_score,
        sentiment_score    = EXCLUDED.sentiment_score,
        key_growth_drivers = EXCLUDED.key_growth_drivers,
        key_risks          = EXCLUDED.key_risks,
        updated_at         = NOW();

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_sync_commentary ON management_commentary;
CREATE TRIGGER trg_sync_commentary
    AFTER INSERT OR UPDATE ON management_commentary
    FOR EACH ROW EXECUTE FUNCTION sync_commentary_to_normalized();
