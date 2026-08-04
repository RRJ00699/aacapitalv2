/** Shared pipeline limits with explicit operational reasons. */
export const PIPELINE_LIMITS = {
  /** Minimum positive operator-supplied count/concurrency to avoid empty/zero worker pools. */
  MIN_POSITIVE_LIMIT: 1,
  /** Owner default: enough for normal active IPO coverage without full-history scans. */
  SNAPSHOT_DEFAULT_IPOS: 25,
  /** Hard guardrail: prevents broad IPO backfills from a snapshot job. */
  SNAPSHOT_HARD_MAX_IPOS: 50,
  /** Owner default: balances Neon pressure and runner throughput for per-IPO Journey reads. */
  SNAPSHOT_DEFAULT_CONCURRENCY: 4,
  /** Hard guardrail: protects Neon/serverless connections from bursty Journey fanout. */
  SNAPSHOT_HARD_MAX_CONCURRENCY: 8,
  /** Publication upper bound: three global snapshots plus the hard maximum per-IPO Journey snapshots. */
  SNAPSHOT_MAX_PUBLICATION_ITEMS: 53,
  /** Journey monitoring window: keep listing-day context for the anchor-lock/review period only. */
  JOURNEY_MONITORING_DAYS: 30,
  /** Fixed query accounting: Command 4 + index 1 + selection 1 + live inputs 2, plus Journey per IPO. */
  SNAPSHOT_FIXED_NEON_QUERIES: 8,
} as const;

export const PIPELINE_SCOPE_DESCRIPTION =
  "mainboard with ISIN: upcoming/open or listing/Journey monitoring window";
