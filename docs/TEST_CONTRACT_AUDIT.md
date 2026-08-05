# Test Contract Audit — Phase A

Status: Active operational-readiness audit.

This audit records assertion strength for the Phase A operational-readiness PR. It is intentionally limited to pre-open capture, pipeline ordering, snapshot publication, and the deferred Journey measurement TODO. No Journey selector logic, schema, deployment, migration, Worker secret rotation, paid extraction, or repository cleanup is included.

## Preserved

- Versioned snapshot unit contracts remain in `lib/versioned-snapshot.test.ts`: active reads, active corruption fallback to previous, and pointer-update failure preserving last-known-good data.
- Route snapshot names and publication allow-list are unchanged for Command, Index, Live Pre-open, and Journey snapshots.
- Pre-open capture continues to write only to the existing `listing_observations` table using the existing `(ipo_id, obs_type, observed_at)` idempotency contract.
- Journey selection logic is unchanged in this PR.

## Restored

- Pre-open capture now has focused tests for outside-window exit, no-listing fast exit, maximum selected count, dry-run no Kite/write behavior, and idempotent write SQL contract.
- Snapshot publication now has an end-to-end integration test that exercises a builder-shaped payload through the publish endpoint, in-memory KV, the user route, and verifies `x-cache: HIT`.
- Pipeline ordering now makes core Python data collection complete before Node setup, `npm ci`, and snapshot publication can fail.

## Intentionally Removed

- No assertions were intentionally removed in this PR.
- No Journey selector assertions were weakened or removed; measurement is deferred rather than implemented here because the selector itself is out of scope.

## Still Missing

- Live production verification of a real listing-day capture window remains missing until a listing-day run with credentials is observed.
- Local/Neon MCP Journey measurements remain missing from Codex Cloud.
- Full deployed Worker/KV verification remains missing because this PR does not deploy.
- Worker Secret rotation tests remain missing by design because Worker Secret implementation is explicitly out of scope.

## Journey Measurement TODO

Pending local/Neon MCP measurement because Codex Cloud cannot reach Neon.

```sql
WITH selector AS (
  SELECT i.id, i.name, i.isin, i.symbol, i.status, i.listing_date
  FROM ipo i
  WHERE i.is_mainboard = true
    AND i.isin IS NOT NULL
    AND (
      i.status IN ('upcoming', 'open')
      OR i.listing_date = (now() AT TIME ZONE 'Asia/Kolkata')::date
      OR i.listing_date >= (now() AT TIME ZONE 'Asia/Kolkata')::date - INTERVAL '60 days'
    )
), excluded AS (
  SELECT i.name, i.isin
  FROM ipo i
  WHERE i.is_mainboard = true
    AND i.isin IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM selector s WHERE s.id = i.id)
)
SELECT 'current_selector_count' AS measurement, count(*)::text AS value FROM selector
UNION ALL
SELECT 'upcoming_open_listing_day_count', count(*)::text FROM selector
WHERE status IN ('upcoming', 'open') OR listing_date = (now() AT TIME ZONE 'Asia/Kolkata')::date
UNION ALL
SELECT 'recently_listed_count', count(*)::text FROM selector
WHERE listing_date < (now() AT TIME ZONE 'Asia/Kolkata')::date
UNION ALL
SELECT 'daily_candle_coverage', count(DISTINCT c.ipo_id)::text FROM price_candles c JOIN selector s ON s.id = c.ipo_id
UNION ALL
SELECT '15m_candle_coverage', count(DISTINCT c.ipo_id)::text FROM market_candles_15m c JOIN selector s ON s.id = c.ipo_id
UNION ALL
SELECT 'excluded_ipo_names_isins', coalesce(json_agg(json_build_object('name', name, 'isin', isin))::text, '[]') FROM excluded;
```
