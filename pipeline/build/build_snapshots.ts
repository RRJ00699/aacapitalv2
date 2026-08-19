/** Canonical snapshot builder (Node/TypeScript).
 * TypeScript is required so this job calls the exact web-domain builders rather than
 * duplicating Command Center, index, Journey, scoring, or listing logic in Python.
 * Reused builders: buildCommand, buildIpoIndex, fetchJourneyCandles, fetchPreopenRows,
 * and scoreListing. Expected cold Node/tsx startup: 1–3 seconds on a hosted runner.
 * Normal DB queries: PIPELINE_LIMITS.SNAPSHOT_FIXED_NEON_QUERIES + selected IPO count.
 */
import pLimit from "p-limit";
import { neon } from "@neondatabase/serverless";
import { buildCommand } from "../../lib/v2/ipo-command";
import { buildIpoIndex } from "../../lib/v2/ipo-index";
import { fetchJourneyCandles } from "../../lib/v2/journey";
import { fetchPreopenRows, scoreListing } from "../../lib/v2/live-preopen";
import type { SqlClient } from "../../lib/v2/sql";
import {
  PIPELINE_LIMITS,
  PIPELINE_SCOPE_DESCRIPTION,
} from "../../lib/config/pipeline";
import { selectJourneyUniverse } from "./journey_universe";
import { detailsFromRow, fetchDetailsRows } from "../../lib/v2/ipo-details";
import {
  assertDetailsPayloadSizes,
  measureDetailsPayloads,
} from "../../lib/v2/details-payload";

export const PRODUCER_CONTRACT = {
  maxBars15m: 160,
  maxTicks: 240,
  maxFailures: 20,
  maxSteps: 80,
  maxPayloadBytes: 128 * 1024,
  fixedQueryCeiling: 16,
  perIpoQueryCeiling: 4,
} as const;

function boundedPayload(name: string, payload: unknown) {
  const bytes = Buffer.byteLength(JSON.stringify(payload));
  if (bytes > PRODUCER_CONTRACT.maxPayloadBytes)
    throw new Error(
      `${name} payload ${bytes} exceeds ${PRODUCER_CONTRACT.maxPayloadBytes}`,
    );
  return { name, payload, payload_bytes: bytes };
}

const arg = (name: string, fallback: string) =>
  process.argv.find((x) => x.startsWith(`--${name}=`))?.split("=")[1] ??
  fallback;

export function snapshotPublishEndpoint(origin: string | undefined): string {
  const raw = (origin ?? "").trim();
  if (!raw) throw new Error("SNAPSHOT_PUBLISH_URL missing");
  let parsed: URL;
  try {
    parsed = new URL(raw);
  } catch {
    throw new Error(
      "SNAPSHOT_PUBLISH_URL malformed; expected site origin like https://example.com",
    );
  }
  if (!/^https?:$/.test(parsed.protocol) || !parsed.host)
    throw new Error(
      "SNAPSHOT_PUBLISH_URL malformed; expected site origin like https://example.com",
    );
  const path = parsed.pathname.replace(/\/+$/, "");
  if (path && path !== "/api/admin/snapshots")
    throw new Error(
      "SNAPSHOT_PUBLISH_URL must be a site origin or /api/admin/snapshots endpoint",
    );
  parsed.pathname = "/api/admin/snapshots";
  parsed.search = "";
  parsed.hash = "";
  return parsed.toString();
}

function requirePublishKey(): string {
  const key = process.env.SNAPSHOT_PUBLISH_KEY?.trim();
  if (!key) throw new Error("SNAPSHOT_PUBLISH_KEY missing");
  return key;
}

function requireDatabaseUrl(schemaSmoke = false): string {
  const url = schemaSmoke
    ? process.env.NEON_READONLY_DATABASE_URL
    : process.env.DATABASE_URL;
  if (!url)
    throw new Error(
      schemaSmoke
        ? "NEON_READONLY_DATABASE_URL is required for schema smoke"
        : "DATABASE_URL is required",
    );
  return url;
}

function safeErrorMessage(error: unknown): string {
  let message = error instanceof Error ? error.message : String(error);
  for (const secret of [
    process.env.DATABASE_URL,
    process.env.NEON_READONLY_DATABASE_URL,
  ]) {
    if (secret) message = message.split(secret).join("[REDACTED]");
  }
  return message;
}

async function atBuilderStage<T>(
  domain: string,
  operation: () => Promise<T>,
): Promise<T> {
  try {
    return await operation();
  } catch (error) {
    throw new Error(
      `[snapshot builder] stage=query; domain=${domain}; PostgreSQL error: ${safeErrorMessage(error)}`,
    );
  }
}

function readOnlySqlClient(sql: SqlClient): SqlClient {
  return ((strings: TemplateStringsArray, ...values: unknown[]) => {
    const statement = strings.join("?").trimStart();
    if (!/^(SELECT|WITH)\b/i.test(statement)) {
      throw new Error("schema smoke blocked a non-read-only SQL statement");
    }
    return sql(strings, ...values);
  }) as SqlClient;
}

async function buildSnapshots(
  sql: SqlClient,
  maxIpos: number,
  concurrency: number,
  schemaSmoke = false,
) {
  const selected = await atBuilderStage("journey-universe", () =>
    selectJourneyUniverse(sql, maxIpos),
  );
  if (!schemaSmoke)
    console.log(
      JSON.stringify({
        selected_count: selected.length,
        selected_isins: selected.map((r) => r.isin),
        max_ipos: maxIpos,
        concurrency,
        expected_neon_queries:
          PIPELINE_LIMITS.SNAPSHOT_FIXED_NEON_QUERIES + selected.length,
        scope: PIPELINE_SCOPE_DESCRIPTION,
      }),
    );
  const limit = pLimit(concurrency);
  // An empty time-window universe must not let schema smoke skip Journey SQL.
  const journeyQueries =
    selected.length || !schemaSmoke
      ? selected.map((r) => ({
          row: r,
          identity: { isin: String(r.isin), sym: String(r.sym) },
        }))
      : [
          {
            row: null,
            identity: { isin: "__SCHEMA_SMOKE__", sym: "__SCHEMA_SMOKE__" },
          },
        ];
  // Schema smoke must execute the full Details SQL even when today's bounded universe is
  // empty. A non-existent sentinel id returns no domain row while PostgreSQL still parses,
  // plans, and validates every new table, column, alias, lateral join and JSON aggregate.
  const detailIds =
    selected.length || !schemaSmoke ? selected.map((row) => row.id) : [-1];
  const [
    command,
    index,
    journeys,
    preopenRows,
    observations,
    levelObservations,
    detailRows,
    healthSteps,
    healthFailures,
    rhpPending,
    paidCalls,
    marketRows,
    breadthRows,
  ] = await Promise.all([
    atBuilderStage("ipo-command", () => buildCommand(sql)),
    atBuilderStage("ipo-index", () => buildIpoIndex(sql)),
    Promise.all(
      journeyQueries.map(({ row, identity }) =>
        limit(async () => ({
          row,
          candles: await atBuilderStage(
            row ? `journey:${String(row.isin)}` : "journey:schema-probe",
            () => fetchJourneyCandles(sql, identity),
          ),
        })),
      ),
    ),
    atBuilderStage("live-preopen", () => fetchPreopenRows(sql)),
    atBuilderStage(
      "preopen-observations",
      () =>
        sql`SELECT DISTINCT ON (o.ipo_id) o.ipo_id,o.ltp,o.buy_qty,o.sell_qty,o.payload,o.observed_at FROM listing_observations o WHERE o.obs_type='preopen' ORDER BY o.ipo_id,o.observed_at DESC`,
    ),
    atBuilderStage(
      "level-observations",
      () =>
        sql`SELECT DISTINCT ON (o.ipo_id) o.ipo_id,o.payload,o.observed_at FROM listing_observations o WHERE o.obs_type='level' ORDER BY o.ipo_id,o.observed_at DESC`,
    ),
    atBuilderStage("ipo-details", () => fetchDetailsRows(sql, detailIds)),
    atBuilderStage(
      "pipeline-health-steps",
      () =>
        sql`SELECT step,ok,error,ran_at FROM pipeline_steps ORDER BY ran_at DESC LIMIT ${PRODUCER_CONTRACT.maxSteps}`,
    ),
    atBuilderStage(
      "pipeline-health-failures",
      () =>
        sql`SELECT step,stderr_tail,failed_at FROM pipeline_failures ORDER BY failed_at DESC LIMIT ${PRODUCER_CONTRACT.maxFailures}`,
    ),
    atBuilderStage(
      "pipeline-health-rhp",
      () =>
        sql`SELECT count(*)::int AS count FROM ipo_stage_state WHERE stage='rhp' AND status IN ('PENDING','FAILED') AND next_retry_at IS NOT NULL`,
    ),
    atBuilderStage(
      "pipeline-health-paid",
      () =>
        sql`SELECT COALESCE(sum(spent_usd),0)::float AS used_usd FROM sbi_haiku_run_log WHERE run_date=current_date`,
    ),
    atBuilderStage(
      "market-india",
      () =>
        sql`SELECT market_regime,vix,pcr,fii_flow,dii_flow,advance_decline_ratio,recommended_exposure,last_updated,captured_at FROM market_snapshot ORDER BY COALESCE(last_updated,captured_at) DESC NULLS LAST LIMIT 1`,
    ),
    atBuilderStage(
      "market-india-breadth",
      () =>
        sql`SELECT value,updated_at FROM platform_config WHERE key='india_breadth' LIMIT 1`,
    ),
  ]);
  const series = await Promise.all(
    selected.map((row) =>
      limit(async () => {
        const [bars15m, ticks] = await Promise.all([
          atBuilderStage(
            `journey-15m:${row.isin}`,
            () =>
              sql`SELECT ts AS timestamp,o AS open,h AS high,l AS low,c AS close,v AS volume FROM market_candles_15m WHERE ipo_id=${row.id} ORDER BY ts DESC LIMIT ${PRODUCER_CONTRACT.maxBars15m}`,
          ),
          atBuilderStage(
            `listing-ticks:${row.isin}`,
            () =>
              sql`SELECT recorded_at AS timestamp,ltp,vwap,day_volume AS cumulative_volume FROM ipo_tick_feed WHERE UPPER(symbol)=${String(row.sym).toUpperCase()} AND recorded_at >= ${row.listing_date}::date AND recorded_at < (${row.listing_date}::date + interval '1 day') ORDER BY recorded_at DESC LIMIT ${PRODUCER_CONTRACT.maxTicks}`,
          ),
        ]);
        const orderedBars = [...bars15m].reverse();
        const orderedTicks = [...ticks].reverse();
        const evaluatedThrough = orderedBars.at(-1)?.timestamp ?? null;
        return {
          row,
          bars15m: orderedBars,
          ticks: orderedTicks,
          evaluatedThrough,
        };
      }),
    ),
  );
  const healthStepRows = healthSteps.map((r: any) => ({
    step: r.step,
    status: r.ok ? "ok" : "failed",
    ran_at: r.ran_at,
    duration_ms: null,
    config_required: null,
    owner_reason: r.ok ? null : r.error,
    error: r.ok ? null : safeErrorMessage(r.error),
  }));
  const lastRunAt = healthStepRows[0]?.ran_at ?? null;
  const health = {
    run_complete:
      healthStepRows.length > 0 &&
      healthStepRows.every((r: any) => r.status === "ok"),
    last_run_at: lastRunAt,
    steps: healthStepRows,
    expected: [
      ...new Map(
        healthStepRows.map((r: any) => [
          r.step,
          { step: r.step, weekly: false },
        ]),
      ).values(),
    ],
    failures: healthFailures.map((r: any) => ({
      step: r.step,
      stderr_tail: safeErrorMessage(String(r.stderr_tail ?? "")).slice(-500),
      failed_at: r.failed_at,
    })),
    owner_actions: healthFailures.length
      ? ["Inspect the bounded failure tail and rerun the owning pipeline step."]
      : [],
    rhp_retry_pending_count: rhpPending[0]?.count ?? null,
    paid_calls: {
      used_usd: paidCalls[0]?.used_usd ?? null,
      cap_usd: process.env.SBI_DAILY_CAP_USD
        ? Number(process.env.SBI_DAILY_CAP_USD)
        : null,
    },
  };
  const market = marketRows[0] ?? {};
  let breadth: any = null;
  try {
    breadth =
      typeof breadthRows[0]?.value === "string"
        ? JSON.parse(breadthRows[0].value)
        : (breadthRows[0]?.value ?? null);
  } catch {
    breadth = null;
  }
  const marketIndia = {
    schema_version: "market-india-v1",
    status: marketRows.length ? "available" : "unavailable",
    evaluated_through: market.last_updated ?? market.captured_at ?? null,
    regime: market.market_regime ?? null,
    breadth,
    pcr: market.pcr ?? null,
    deploy_band: market.recommended_exposure ?? null,
    fii: market.fii_flow ?? null,
    dii: market.dii_flow ?? null,
    global_cache: null,
  };
  const latest = new Map(observations.map((o) => [String(o.ipo_id), o]));
  const latestLevel = new Map(
    levelObservations.map((o) => [String(o.ipo_id), o]),
  );
  const now = new Date().toISOString();
  const producerSnapshots = series.flatMap(
    ({ row, bars15m, ticks, evaluatedThrough }) => {
      const meta = {
        isin: row.isin,
        symbol: row.sym,
        listing_date: row.listing_date,
        freshness: { evaluated_through: evaluatedThrough, generated_at: now },
      };
      return [
        boundedPayload(
          `journey-15m:isin:${String(row.isin).toUpperCase()}:v1`,
          { schema_version: "journey-15m-v1", ...meta, bars: bars15m },
        ),
        boundedPayload(
          `listing-cumulative-volume:isin:${String(row.isin).toUpperCase()}:v1`,
          {
            schema_version: "listing-cumulative-volume-v1",
            ...meta,
            points: ticks.map((t: any) => ({
              timestamp: t.timestamp,
              cumulative_volume: t.cumulative_volume ?? null,
            })),
          },
        ),
        boundedPayload(
          `listing-ticks:isin:${String(row.isin).toUpperCase()}:v1`,
          { schema_version: "listing-ticks-v1", ...meta, ticks },
        ),
      ];
    },
  );
  const globals = [
    { name: "ipo-command:v6", payload: command },
    { name: "ipo:index:v3", payload: index },
    boundedPayload("pipeline-health:v1", health),
    boundedPayload("market-india:v1", marketIndia),
    ...producerSnapshots,
    {
      name: "ipo-live-preopen:v2",
      payload: {
        ok: true,
        window: "listing_date = IST-today",
        book_live: false,
        live_overlay: "BLOCKED",
        degraded: "Kite credential automation is not proven safe",
        count: preopenRows.length,
        listings: preopenRows.map((r) => ({
          ...scoreListing(r),
          latest_observation: latest.get(String(r.ipo_id)) ?? null,
        })),
        fetchedAt: now,
      },
    },
    ...journeys
      .filter(({ row }) => row !== null)
      .map(({ row, candles }) => ({
        name: `journey:isin:${String(row!.isin).toUpperCase()}:v1`,
        payload: {
          isin: row!.isin,
          sym: row!.sym,
          rows: candles,
          level_observation: latestLevel.get(String(row!.id)) ?? null,
          generated_at: now,
        },
      })),
  ];
  const details = detailRows.map((row) => ({
    name: `ipo-details:isin:${String(row.isin).toUpperCase()}:v1`,
    payload: detailsFromRow(row, now),
  }));
  const measuredBytes = globals.map((s: any) => ({
    name: s.name,
    bytes: s.payload_bytes ?? Buffer.byteLength(JSON.stringify(s.payload)),
  }));
  if (!schemaSmoke)
    console.log(
      JSON.stringify({
        producer_contract: {
          query_ceiling:
            PRODUCER_CONTRACT.fixedQueryCeiling +
            selected.length * PRODUCER_CONTRACT.perIpoQueryCeiling,
          max_payload_bytes: PRODUCER_CONTRACT.maxPayloadBytes,
          measured: measuredBytes,
        },
      }),
    );
  return { globals, details };
}

async function publishBatch(
  endpoint: string,
  key: string,
  snapshots: Array<{ name: string; payload: unknown }>,
  label: string,
) {
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "content-type": "application/json", "x-aac-key": key },
    body: JSON.stringify({ snapshots }),
  });
  if (!response.ok)
    throw new Error(
      `${label} publication failed ${response.status}: ${await response.text()}`,
    );
  const result = (await response.json()) as {
    published?: Record<string, string>;
  };
  if (!result.published)
    throw new Error(`${label} publication response omitted versions`);
  console.log(
    JSON.stringify({
      stage: "publication",
      label,
      published: result.published,
    }),
  );
  return result.published;
}

function fixtureSqlClient(): SqlClient {
  let queryCount = 0;
  return (async (strings: TemplateStringsArray) => {
    const query = strings.join("?");
    queryCount += 1;
    // This fixture executes every real snapshot query. Keep the guard here rather
    // than source-grepping so interpolated tagged-template SQL is also checked.
    if (/\bi\.name\b/i.test(query))
      throw new Error(
        `stale ipo identity column in fixture query #${queryCount}: i.name`,
      );
    if (
      /SELECT DISTINCT i\.id/.test(query) &&
      !/i\.listing_date >= \(\s*\(now\(\) AT TIME ZONE 'Asia\/Kolkata'\)::date\s*- \(\?::int\)\s*\)/.test(
        query,
      )
    ) {
      throw new Error(
        "Journey monitoring-days SQL parameter must be explicitly cast to int",
      );
    }
    if (
      process.env.SNAPSHOT_TEST_POSTGRES_ERROR === "1" &&
      /SELECT DISTINCT i\.id/.test(query)
    ) {
      throw new Error("column i.forced_missing does not exist");
    }
    if (/COALESCE\(\(SELECT json_agg/.test(query))
      return [
        {
          ipo_id: 1,
          isin: "INE000000001",
          sym: "FIXTURE",
          company_name: "Fixture IPO",
          issue_price: 100,
          band_lo: 95,
          band_hi: 100,
          issue_size_cr: 500,
          score: 2.5,
          score_band: "STRONG",
          engine_version: "v2-score-2",
          valuation_computed_at: "2026-08-06T00:00:00Z",
          pe: 20,
          pb: 2,
          pe_source: "rhp_computed:price/eps_post",
          pb_source: "proxy:issue_size/net_worth",
          fair_value_lo: 110,
          fair_value_hi: 125,
          inputs_used: {
            pe_source: "rhp_computed:price/eps_post",
            pb_source: "proxy:issue_size/net_worth",
          },
          missing_inputs: [],
          findings: { litigation: ["No material litigation"] },
          analysis_model: "fixture-model",
          analysis_prompt_version: "v2-full",
          analysis_confidence: 0.9,
          analyzed_at: "2026-08-06T00:00:00Z",
          red_flag_count: 0,
          junk_signals: [],
          fundamental_verdict: "GOOD",
          decision_reasons: ["complete"],
          decision_evidence: { score_band: "STRONG" },
          decided_at: "2026-08-06T00:00:00Z",
          verified_evidence: [
            {
              excerpt: "Verified fixture excerpt",
              page_number: 12,
              doc_id: 1,
              document: {
                doc_type: "rhp",
                url: "https://example.test/rhp.pdf",
                sha256: "abc",
                page_count: 100,
              },
              category: "risk",
              direction: "neutral",
              source_type: "RHP",
            },
          ],
        },
      ];
    if (/FROM pipeline_steps/.test(query))
      return [
        {
          step: "snapshot publication",
          ok: true,
          error: null,
          ran_at: "2026-08-19T00:00:00Z",
        },
      ];
    if (/FROM pipeline_failures/.test(query)) return [];
    if (/FROM ipo_stage_state/.test(query)) return [{ count: 0 }];
    if (/FROM sbi_haiku_run_log/.test(query)) return [{ used_usd: 0 }];
    if (/FROM market_snapshot/.test(query))
      return [
        {
          market_regime: "NEUTRAL",
          vix: 14,
          pcr: null,
          fii_flow: null,
          dii_flow: null,
          recommended_exposure: 50,
          last_updated: "2026-08-19T00:00:00Z",
        },
      ];
    if (/FROM platform_config/.test(query))
      return [
        {
          value: JSON.stringify({ adv: 10, dec: 8, unch: 2 }),
          updated_at: "2026-08-19T00:00:00Z",
        },
      ];
    if (/FROM market_candles_15m/.test(query))
      return [
        {
          timestamp: "2026-08-19T04:00:00Z",
          open: 100,
          high: 102,
          low: 99,
          close: 101,
          volume: 1000,
        },
      ];
    if (/FROM ipo_tick_feed/.test(query))
      return [
        {
          timestamp: "2026-08-19T04:00:00Z",
          ltp: 101,
          vwap: 100.5,
          cumulative_volume: 5000,
        },
      ];
    if (/SELECT DISTINCT i\.id/.test(query))
      return [
        {
          id: 1,
          isin: "INE000000001",
          sym: "FIXTURE",
          listing_date: null,
          company_name: "Fixture IPO",
          reason_selected: "fixture",
        },
      ];
    if (
      /SELECT i\.id AS ipo_id/.test(query) &&
      !/WHERE i\.listing_date = \(NOW/.test(query)
    )
      return [{ ipo_id: 1, sym: "FIXTURE", company_name: "Fixture IPO" }];
    if (/SELECT name_display AS company_name/.test(query))
      return [
        { sym: "FIXTURE", isin: "INE000000001", company_name: "Fixture IPO" },
      ];
    return [];
  }) as SqlClient;
}

export async function main() {
  const maxIpos = Math.max(
    PIPELINE_LIMITS.MIN_POSITIVE_LIMIT,
    Math.min(
      PIPELINE_LIMITS.SNAPSHOT_HARD_MAX_IPOS,
      Number(
        arg(
          "limit",
          process.env.SNAPSHOT_MAX_IPOS ||
            String(PIPELINE_LIMITS.SNAPSHOT_DEFAULT_IPOS),
        ),
      ),
    ),
  );
  const concurrency = Math.max(
    PIPELINE_LIMITS.MIN_POSITIVE_LIMIT,
    Math.min(
      PIPELINE_LIMITS.SNAPSHOT_HARD_MAX_CONCURRENCY,
      Number(
        arg(
          "concurrency",
          String(PIPELINE_LIMITS.SNAPSHOT_DEFAULT_CONCURRENCY),
        ),
      ),
    ),
  );
  const dryRun = process.argv.includes("--dry-run");
  const schemaSmoke = process.argv.includes("--schema-smoke");
  if (schemaSmoke && process.env.SNAPSHOT_TEST_FIXTURE === "1")
    throw new Error(
      "schema smoke requires real Neon SQL; fixture is not allowed",
    );
  const publishEndpoint =
    schemaSmoke || dryRun
      ? null
      : snapshotPublishEndpoint(process.env.SNAPSHOT_PUBLISH_URL);
  const key = schemaSmoke || dryRun ? null : requirePublishKey();

  const fixture = process.env.SNAPSHOT_TEST_FIXTURE === "1";
  const realSql = fixture
    ? null
    : (neon(requireDatabaseUrl(schemaSmoke)) as unknown as SqlClient);
  const sql = fixture
    ? fixtureSqlClient()
    : schemaSmoke
      ? readOnlySqlClient(realSql!)
      : realSql!;
  const { globals, details } = await buildSnapshots(
    sql,
    maxIpos,
    concurrency,
    schemaSmoke,
  );
  if (fixture)
    console.log(JSON.stringify({ snapshot_fixture_sql_verified: true }));
  if (schemaSmoke) {
    console.log(
      JSON.stringify({
        stage: "schema-smoke",
        domain: "snapshot-builder",
        selected_count: globals.filter((s) => s.name.startsWith("journey:"))
          .length,
        details_query_count: 1,
        status: "success",
      }),
    );
    return;
  }

  const { measured, report } = measureDetailsPayloads(details);
  console.log(
    JSON.stringify({
      details_payload_measurement: report,
      configured_max_bytes: PIPELINE_LIMITS.DETAILS_MAX_PAYLOAD_BYTES,
      details_query_count: 1,
    }),
  );
  assertDetailsPayloadSizes(
    measured,
    PIPELINE_LIMITS.DETAILS_MAX_PAYLOAD_BYTES,
  );
  if (dryRun) return;
  console.log(
    JSON.stringify({
      payload_bytes: Buffer.byteLength(JSON.stringify({ snapshots: globals })),
      snapshots: globals.length,
      publish_endpoint: publishEndpoint,
    }),
  );
  await publishBatch(publishEndpoint!, key!, globals, "global/Journey");
  for (
    let offset = 0;
    offset < details.length;
    offset += PIPELINE_LIMITS.DETAILS_PUBLICATION_BATCH_SIZE
  ) {
    const batch = details.slice(
      offset,
      offset + PIPELINE_LIMITS.DETAILS_PUBLICATION_BATCH_SIZE,
    );
    const number =
      Math.floor(offset / PIPELINE_LIMITS.DETAILS_PUBLICATION_BATCH_SIZE) + 1;
    try {
      await publishBatch(
        publishEndpoint!,
        key!,
        batch,
        `details batch ${number}`,
      );
    } catch (error) {
      const failingIsins = batch.map((x) => x.name.split(":")[2]);
      console.error(
        JSON.stringify({
          stage: "details-publication",
          details_batch: number,
          failing_isins: failingIsins,
          error: error instanceof Error ? error.message : String(error),
        }),
      );
      throw error;
    }
  }
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : String(err));
  process.exit(1);
});
