-- ═══════════════════════════════════════════════════════════════════════
-- dedup_merge.sql — merge Ltd/Limited/&-and twin rows in ipo_intelligence
-- Census 2026-07-16: 9 pairs. Pair (861,908) EXCLUDED — conflicting
-- symbols RMC vs UEL = possibly different entities → manual review only.
-- Keeper rule: the row with nse_symbol; if neither has one, the lower id.
-- Merge: fill-empty (COALESCE) EVERY column from donor → keeper, repoint
-- name-keyed dependents, delete donor. Run PREVIEW first. Then BEGIN block.
-- ═══════════════════════════════════════════════════════════════════════

-- ── PREVIEW: what will merge into what ──────────────────────────────────
WITH pairs(keeper, donor) AS (VALUES
  (1077,1153),(1151,1155),(704,319),(972,1135),
  (979,1136),(1075,1154),(990,1125),(1021,1109))
SELECT p.keeper, k.company_name AS keeper_name, k.nse_symbol AS keeper_sym,
       p.donor,  d.company_name AS donor_name,  d.nse_symbol AS donor_sym
FROM pairs p
JOIN ipo_intelligence k ON k.id = p.keeper
JOIN ipo_intelligence d ON d.id = p.donor;

-- ── APPLY (run after preview looks right) ───────────────────────────────
BEGIN;

DO $$
DECLARE
  pair RECORD;
  col  RECORD;
  keeper_name TEXT;
  donor_name  TEXT;
  dep TEXT;
  namecol TEXT;
BEGIN
  FOR pair IN
    SELECT * FROM (VALUES
      (1077,1153),(1151,1155),(704,319),(972,1135),
      (979,1136),(1075,1154),(990,1125),(1021,1109)
    ) AS t(keeper, donor)
  LOOP
    -- fill-empty every column (except identity/pk) donor -> keeper
    FOR col IN
      SELECT column_name FROM information_schema.columns
      WHERE table_name = 'ipo_intelligence'
        AND column_name NOT IN ('id','company_name')
    LOOP
      EXECUTE format(
        'UPDATE ipo_intelligence k SET %1$I = COALESCE(k.%1$I, d.%1$I)
         FROM ipo_intelligence d WHERE k.id = %2$s AND d.id = %3$s',
        col.column_name, pair.keeper, pair.donor);
    END LOOP;

    SELECT company_name INTO keeper_name FROM ipo_intelligence WHERE id = pair.keeper;
    SELECT company_name INTO donor_name  FROM ipo_intelligence WHERE id = pair.donor;

    -- name-keyed dependents: keep keeper-keyed row if it exists, else repoint
    FOREACH dep IN ARRAY ARRAY['ipo_verdicts','ipo_flags','ipo_rhp_intel','ipo_broker_consensus']
    LOOP
      namecol := CASE WHEN dep = 'ipo_broker_consensus' THEN 'company' ELSE 'company_name' END;
      IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = dep) THEN
        EXECUTE format(
          'DELETE FROM %1$I WHERE %2$I = $1 AND EXISTS
             (SELECT 1 FROM %1$I x WHERE x.%2$I = $2)', dep, namecol)
          USING donor_name, keeper_name;
        EXECUTE format(
          'UPDATE %1$I SET %2$I = $2 WHERE %2$I = $1', dep, namecol)
          USING donor_name, keeper_name;
      END IF;
    END LOOP;

    DELETE FROM ipo_intelligence WHERE id = pair.donor;
    RAISE NOTICE 'merged % (%) <- % (%)', pair.keeper, keeper_name, pair.donor, donor_name;
  END LOOP;

  RAISE NOTICE 'SKIPPED pair (861 RMC, 908 UEL) — conflicting symbols, manual review';
END $$;

COMMIT;

-- ── VERIFY: census should return only the skipped pair (or nothing) ─────
WITH n AS (
  SELECT id, company_name,
    trim(regexp_replace(regexp_replace(regexp_replace(
      lower(company_name), '\y(limited|ltd\.?|pvt\.?|private|and)\y',' ','g'),
      '&',' ','g'), '[^a-z0-9]+',' ','g')) AS canon
  FROM ipo_intelligence)
SELECT canon, COUNT(*), array_agg(company_name) FROM n
GROUP BY canon HAVING COUNT(*) > 1;
