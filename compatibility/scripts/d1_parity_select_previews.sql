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
 SELECT id,status,
   CASE WHEN listing_date IS NOT NULL AND date(listing_date)<=date('now') THEN 'LISTED'
        WHEN close_date IS NOT NULL AND date(close_date)<date('now') THEN 'CLOSED'
        WHEN open_date IS NOT NULL AND date('now') BETWEEN date(open_date) AND date(close_date) THEN 'OPEN'
        ELSE 'ANNOUNCED' END proposed_status
 FROM ipo)
SELECT status,proposed_status,COUNT(*) proposed_writes FROM proposed
GROUP BY status,proposed_status ORDER BY 1,2;

-- Audit all currently known date-bearing columns. The checker discovers any additional
-- DATE/*_date columns dynamically rather than relying only on this list.
SELECT 'ipo.listing_date' field,id,listing_date value FROM ipo
 WHERE listing_date IS NOT NULL AND listing_date NOT GLOB '????-??-??'
UNION ALL SELECT 'ipo.open_date',id,open_date FROM ipo
 WHERE open_date IS NOT NULL AND open_date NOT GLOB '????-??-??'
UNION ALL SELECT 'ipo.close_date',id,close_date FROM ipo
 WHERE close_date IS NOT NULL AND close_date NOT GLOB '????-??-??';

-- Proven gap defects. ipo_id=301 remains isolated for inspection, never force-fixed.
SELECT o.ipo_id,o.gap_pct,o.pool,o.listing_open,x.issue_price,
       ROUND((o.listing_open-x.issue_price)/x.issue_price*100,4) proposed_gap,
       CASE WHEN (o.listing_open-x.issue_price)/x.issue_price*100 < 0 THEN 'NEGATIVE'
            WHEN (o.listing_open-x.issue_price)/x.issue_price*100 < 15 THEN 'FLAT'
            WHEN (o.listing_open-x.issue_price)/x.issue_price*100 < 50 THEN 'WARM'
            ELSE 'HEAVY' END proposed_pool
FROM listing_outcomes o JOIN ipo_issue x ON x.ipo_id=o.ipo_id
WHERE ABS(o.gap_pct)>300 AND o.ipo_id<>301;
SELECT o.*,x.issue_price,(o.listing_open-x.issue_price)/x.issue_price*100 computed_gap
FROM listing_outcomes o LEFT JOIN ipo_issue x ON x.ipo_id=o.ipo_id WHERE o.ipo_id=301;

-- Research parity and coverage previews.
SELECT (SELECT COUNT(*) FROM raw_objects) raw_objects,
       (SELECT COUNT(*) FROM ipomatrix_raw_stage) staged,
       (SELECT COUNT(*) FROM ipomatrix_raw_stage_chunks) chunks;
SELECT ipo_id,COUNT(*) snapshots FROM neon_subscription_snapshots GROUP BY ipo_id ORDER BY ipo_id;
SELECT COUNT(*) proposed_listing_bands FROM neon_ipo_listing_band;
SELECT COUNT(*) proposed_anchor_summary FROM neon_anchor_summary;
SELECT COUNT(*) proposed_anchor_allocations FROM neon_anchor_allocations;
SELECT COUNT(DISTINCT i.id) ipo_count,COUNT(DISTINCT v.ipo_id) covered,
       COUNT(DISTINCT i.id)-COUNT(DISTINCT v.ipo_id) missing
FROM ipo i LEFT JOIN valuation_runs v ON v.ipo_id=i.id;

-- Outcomes recoverable only from stored D1 candles; no market API is called.
SELECT i.id,COUNT(b.d) candles,MIN(b.d) first_candle,
       MAX(CASE WHEN b.d=i.listing_date THEN 1 ELSE 0 END) has_listing_candle
FROM ipo i LEFT JOIN listing_outcomes o ON o.ipo_id=i.id
LEFT JOIN market_bars b ON b.ipo_id=i.id
WHERE date(i.listing_date)<date('now') AND o.ipo_id IS NULL
GROUP BY i.id ORDER BY i.id;

SELECT i.id,i.isin,i.name_norm FROM ipo i LEFT JOIN ipo_issue x ON x.ipo_id=i.id
WHERE x.ipo_id IS NULL ORDER BY i.id;
SELECT o.ipo_id,o.gap_pct,o.pool FROM listing_outcomes o WHERE o.pool IS NULL ORDER BY o.ipo_id;
