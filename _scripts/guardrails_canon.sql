-- ═══════════════════════════════════════════════════════════════════════
-- guardrails_canon.sql — GUARDRAIL A: canonical-name uniqueness (owner-run)
-- Run each statement top to bottom in the SQL console.
-- PREREQUISITE: resolve pair id 861 (RMC) vs 908 (UEL) first — if they are
-- true duplicates merge them; if different companies fix the wrong name.
-- The index CANNOT be created while any canon collision exists.
-- ═══════════════════════════════════════════════════════════════════════

-- 1) PRE-FLIGHT: must return ZERO rows before running step 2/3
SELECT regexp_replace(lower(company_name),
         '\y(ltd|limited|pvt|private|ipo|and)\y|&|[^a-z0-9]', '', 'g') AS canon,
       COUNT(*), array_agg(id), array_agg(company_name)
FROM ipo_intelligence
GROUP BY 1 HAVING COUNT(*) > 1;

-- 2) the SQL twin of _scripts/lib/canon.py (keep the two in lockstep)
CREATE OR REPLACE FUNCTION canon_company(name TEXT) RETURNS TEXT
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $f$
  SELECT regexp_replace(lower(coalesce(name,'')),
         '\y(ltd|limited|pvt|private|ipo|and)\y|&|[^a-z0-9]', '', 'g')
$f$;

-- 3) THE GUARD: a Ltd/Limited/&-variant twin can no longer be inserted at all.
--    Any scraper attempting one gets a unique-violation the same night.
CREATE UNIQUE INDEX IF NOT EXISTS ux_ipo_intelligence_canon
  ON ipo_intelligence (canon_company(company_name));

-- 4) verify
SELECT indexname FROM pg_indexes
WHERE tablename='ipo_intelligence' AND indexname='ux_ipo_intelligence_canon';
