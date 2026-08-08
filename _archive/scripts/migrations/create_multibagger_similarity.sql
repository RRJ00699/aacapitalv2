-- scripts/migrations/create_multibagger_similarity.sql
-- AACapital Historical Similarity Engine output table.

CREATE TABLE IF NOT EXISTS multibagger_similarity (
  id BIGSERIAL PRIMARY KEY,
  symbol TEXT NOT NULL,
  similar_to TEXT NOT NULL,
  historical_event_id BIGINT,
  historical_start_date DATE,
  historical_end_date DATE,
  historical_return_pct NUMERIC,
  historical_tier TEXT,
  similarity_score NUMERIC NOT NULL,
  dtw_distance NUMERIC,
  current_shape JSONB,
  historical_shape JSONB,
  p_2x NUMERIC,
  p_5x NUMERIC,
  p_10x NUMERIC,
  status TEXT NOT NULL DEFAULT 'ACTIVE',
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(symbol, similar_to, historical_event_id)
);

CREATE INDEX IF NOT EXISTS idx_multibagger_similarity_symbol
  ON multibagger_similarity(symbol, similarity_score DESC);

CREATE INDEX IF NOT EXISTS idx_multibagger_similarity_score
  ON multibagger_similarity(similarity_score DESC);

CREATE INDEX IF NOT EXISTS idx_multibagger_similarity_updated
  ON multibagger_similarity(updated_at DESC);
