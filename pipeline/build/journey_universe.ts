import type { SqlClient } from "../../lib/v2/sql";
import { PIPELINE_LIMITS } from "../../lib/config/pipeline";

export type JourneyUniverseRow = {
  id: number | string;
  isin: string;
  sym: string;
  listing_date: string | Date | null;
  company_name: string | null;
  reason_selected: string;
};

export async function selectJourneyUniverse(sql: SqlClient, maxIpos: number = PIPELINE_LIMITS.SNAPSHOT_DEFAULT_IPOS) {
  const bounded = Math.max(
    PIPELINE_LIMITS.MIN_POSITIVE_LIMIT,
    Math.min(PIPELINE_LIMITS.SNAPSHOT_HARD_MAX_IPOS, maxIpos),
  );
  return sql`
    SELECT DISTINCT i.id, i.isin, UPPER(COALESCE(i.symbol,'')) AS sym, i.listing_date,
      i.name_display AS company_name,
      CASE
        WHEN iss.open_date <= (now() AT TIME ZONE 'Asia/Kolkata')::date
          AND iss.close_date >= (now() AT TIME ZONE 'Asia/Kolkata')::date THEN 'open IPO issue'
        WHEN iss.open_date > (now() AT TIME ZONE 'Asia/Kolkata')::date THEN 'upcoming IPO issue'
        WHEN i.listing_date = (now() AT TIME ZONE 'Asia/Kolkata')::date THEN 'listing-day IPO'
        ELSE 'within Journey monitoring window'
      END AS reason_selected
    FROM ipo i JOIN ipo_issue iss ON iss.ipo_id=i.id
    WHERE i.is_mainboard=true AND i.isin IS NOT NULL
      AND (iss.open_date >= (now() AT TIME ZONE 'Asia/Kolkata')::date
        OR iss.close_date >= (now() AT TIME ZONE 'Asia/Kolkata')::date
        OR i.listing_date >= (
          (now() AT TIME ZONE 'Asia/Kolkata')::date
          - (${PIPELINE_LIMITS.JOURNEY_MONITORING_DAYS}::int)
        ))
    ORDER BY i.listing_date DESC NULLS LAST LIMIT ${bounded}` as Promise<JourneyUniverseRow[]>;
}
