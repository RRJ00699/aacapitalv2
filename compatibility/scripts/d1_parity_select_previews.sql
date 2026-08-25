-- READ ONLY. Run against one bulk D1 export before considering any repair.
-- Every statement is a SELECT; this file intentionally contains no mutation.

-- P1 identity: exact ISIN first, then exact name_norm; fuzzy matching is forbidden.
-- neon_ipo is an owner-supplied local import of the read-only Neon export.
SELECT d.id,d.isin,d.name_norm,d.nse_symbol,n.symbol AS proposed_nse_symbol,'ISIN' match_kind
FROM ipo d JOIN neon_ipo n ON n.isin=d.isin
WHERE d.nse_symbol IS NULL AND d.isin IS NOT NULL AND n.symbol IS NOT NULL
UNION ALL
SELECT d.id,d.isin,d.name_norm,d.nse_symbol,n.symbol,'NAME_NORM'
FROM ipo d JOIN neon_ipo n ON n.name_norm=d.name_norm
WHERE d.nse_symbol IS NULL AND d.name_norm IS NOT NULL AND n.symbol IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM neon_ipo x WHERE x.isin=d.isin AND d.isin IS NOT NULL)
ORDER BY 1;

-- Deterministic lifecycle as of the SQLite clock; report this distribution before write.
WITH proposed AS (
 SELECT i.id,i.status,
   CASE WHEN x.listing_date IS NOT NULL AND date(x.listing_date)<date('now') THEN 'LISTED'
        WHEN x.close_date IS NOT NULL AND date(x.close_date)<date('now')
             AND x.listing_date IS NOT NULL AND date(x.listing_date)>=date('now') THEN 'ALLOTTED'
        WHEN x.open_date IS NOT NULL AND x.close_date IS NOT NULL
             AND date('now') BETWEEN date(x.open_date) AND date(x.close_date) THEN 'OPEN'
        WHEN x.open_date IS NOT NULL AND date(x.open_date)>date('now') THEN 'UPCOMING'
        ELSE 'ANNOUNCED' END proposed_status
 FROM ipo i LEFT JOIN ipo_issue x ON x.ipo_id=i.id)
SELECT status,proposed_status,COUNT(*) proposed_writes FROM proposed
GROUP BY status,proposed_status ORDER BY 1,2;

-- Audit all currently known date-bearing columns. The checker discovers any additional
-- DATE/*_date columns dynamically rather than relying only on this list.
SELECT 'ipo_issue.listing_date' field,ipo_id,listing_date value FROM ipo_issue
 WHERE listing_date IS NOT NULL AND listing_date NOT GLOB '????-??-??'
UNION ALL SELECT 'ipo_issue.open_date',ipo_id,open_date FROM ipo_issue
 WHERE open_date IS NOT NULL AND open_date NOT GLOB '????-??-??'
UNION ALL SELECT 'ipo_issue.close_date',ipo_id,close_date FROM ipo_issue
 WHERE close_date IS NOT NULL AND close_date NOT GLOB '????-??-??'
UNION ALL SELECT 'ipo_issue.allotment_date',ipo_id,allotment_date FROM ipo_issue
 WHERE allotment_date IS NOT NULL AND allotment_date NOT GLOB '????-??-??'
UNION ALL SELECT 'ipo_issue.lock30_date',ipo_id,lock30_date FROM ipo_issue
 WHERE lock30_date IS NOT NULL AND lock30_date NOT GLOB '????-??-??'
UNION ALL SELECT 'ipo_issue.lock90_date',ipo_id,lock90_date FROM ipo_issue
 WHERE lock90_date IS NOT NULL AND lock90_date NOT GLOB '????-??-??';

-- Proven gap defects. ipo_id=301 remains isolated for inspection, never force-fixed.
SELECT o.ipo_id,o.gap_pct,o.pool,o.listing_open,x.issue_price_rs,
       ROUND((CAST(o.listing_open AS REAL)-CAST(x.issue_price_rs AS REAL))
             /CAST(x.issue_price_rs AS REAL)*100,4) proposed_gap,
       CASE WHEN (CAST(o.listing_open AS REAL)-CAST(x.issue_price_rs AS REAL))/CAST(x.issue_price_rs AS REAL)*100 < 0 THEN 'NEGATIVE'
            WHEN (CAST(o.listing_open AS REAL)-CAST(x.issue_price_rs AS REAL))/CAST(x.issue_price_rs AS REAL)*100 < 15 THEN 'FLAT'
            WHEN (CAST(o.listing_open AS REAL)-CAST(x.issue_price_rs AS REAL))/CAST(x.issue_price_rs AS REAL)*100 < 50 THEN 'WARM'
            ELSE 'HEAVY' END proposed_pool
FROM listing_outcomes o JOIN ipo_issue x ON x.ipo_id=o.ipo_id
WHERE CAST(x.issue_price_rs AS REAL)>0 AND ABS(CAST(o.gap_pct AS REAL))>300 AND o.ipo_id<>301;
SELECT o.*,x.issue_price_rs,
       (CAST(o.listing_open AS REAL)-CAST(x.issue_price_rs AS REAL))/CAST(x.issue_price_rs AS REAL)*100 computed_gap
FROM listing_outcomes o LEFT JOIN ipo_issue x ON x.ipo_id=o.ipo_id WHERE o.ipo_id=301;

-- Research parity and coverage previews.
SELECT (SELECT COUNT(*) FROM raw_objects) raw_objects,
       (SELECT COUNT(*) FROM ipomatrix_raw_stage) staged,
       (SELECT COUNT(*) FROM ipomatrix_raw_stage_chunks) chunks;
SELECT ipo_id,COUNT(*) snapshots FROM neon_subscription_snapshots GROUP BY ipo_id ORDER BY ipo_id;
-- Historical reader evidence establishes ipo_id + daily band_pct (5/10/20). The
-- remaining key/date/provenance columns must come from the owner Neon schema export.
SELECT band_pct,COUNT(*) proposed_listing_bands FROM neon_ipo_listing_band
GROUP BY band_pct ORDER BY CAST(band_pct AS REAL);
SELECT COUNT(*) proposed_anchor_summary FROM neon_anchor_summary;
SELECT COUNT(*) proposed_anchor_allocations FROM neon_anchor_allocations;
SELECT COUNT(DISTINCT i.id) ipo_count,COUNT(DISTINCT v.ipo_id) covered,
       COUNT(DISTINCT i.id)-COUNT(DISTINCT v.ipo_id) missing
FROM ipo i LEFT JOIN valuation_runs v ON v.ipo_id=i.id;

-- Outcomes recoverable only from stored D1 candles; no market API is called.
SELECT i.id,COUNT(b.ts) candles,MIN(b.ts) first_candle,
       MAX(CASE WHEN date(b.ts)=date(x.listing_date) THEN 1 ELSE 0 END) has_listing_candle
FROM ipo i LEFT JOIN listing_outcomes o ON o.ipo_id=i.id
JOIN ipo_issue x ON x.ipo_id=i.id
LEFT JOIN market_bars b ON b.ipo_id=i.id AND b.interval='1d'
WHERE date(x.listing_date)<date('now') AND o.ipo_id IS NULL
GROUP BY i.id ORDER BY i.id;

SELECT i.id,i.isin,i.name_norm FROM ipo i LEFT JOIN ipo_issue x ON x.ipo_id=i.id
WHERE x.ipo_id IS NULL ORDER BY i.id;
SELECT o.ipo_id,o.gap_pct,o.pool FROM listing_outcomes o WHERE o.pool IS NULL ORDER BY o.ipo_id;
