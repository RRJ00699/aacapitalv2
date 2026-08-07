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
import { PIPELINE_LIMITS, PIPELINE_SCOPE_DESCRIPTION } from "../../lib/config/pipeline";
import { selectJourneyUniverse } from "./journey_universe";
import { detailsFromRow, fetchDetailsRows } from "../../lib/v2/ipo-details";
import { assertDetailsPayloadSizes, measureDetailsPayloads } from "../../lib/v2/details-payload";

const arg = (name: string, fallback: string) => process.argv.find(x => x.startsWith(`--${name}=`))?.split("=")[1] ?? fallback;

export function snapshotPublishEndpoint(origin: string | undefined): string {
  const raw = (origin ?? "").trim();
  if (!raw) throw new Error("SNAPSHOT_PUBLISH_URL missing");
  let parsed: URL;
  try { parsed = new URL(raw); } catch { throw new Error("SNAPSHOT_PUBLISH_URL malformed; expected site origin like https://example.com"); }
  if (!/^https?:$/.test(parsed.protocol) || !parsed.host) throw new Error("SNAPSHOT_PUBLISH_URL malformed; expected site origin like https://example.com");
  const path = parsed.pathname.replace(/\/+$/, "");
  if (path && path !== "/api/admin/snapshots") throw new Error("SNAPSHOT_PUBLISH_URL must be a site origin or /api/admin/snapshots endpoint");
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
  if (!url) throw new Error(schemaSmoke ? "NEON_READONLY_DATABASE_URL is required for schema smoke" : "DATABASE_URL is required");
  return url;
}

function safeErrorMessage(error: unknown): string {
  let message = error instanceof Error ? error.message : String(error);
  for (const secret of [process.env.DATABASE_URL, process.env.NEON_READONLY_DATABASE_URL]) {
    if (secret) message = message.split(secret).join("[REDACTED]");
  }
  return message;
}

async function atBuilderStage<T>(domain: string, operation: () => Promise<T>): Promise<T> {
  try {
    return await operation();
  } catch (error) {
    throw new Error(`[snapshot builder] stage=query; domain=${domain}; PostgreSQL error: ${safeErrorMessage(error)}`);
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

async function buildSnapshots(sql: SqlClient, maxIpos: number, concurrency: number, schemaSmoke = false) {
  const selected = await atBuilderStage("journey-universe", () => selectJourneyUniverse(sql, maxIpos));
  if (!schemaSmoke) console.log(JSON.stringify({ selected_count: selected.length, selected_isins: selected.map(r => r.isin), max_ipos: maxIpos,
    concurrency, expected_neon_queries: PIPELINE_LIMITS.SNAPSHOT_FIXED_NEON_QUERIES + selected.length, scope: PIPELINE_SCOPE_DESCRIPTION }));
  const limit = pLimit(concurrency);
  // An empty time-window universe must not let schema smoke skip Journey SQL.
  const journeyQueries = selected.length || !schemaSmoke
    ? selected.map(r => ({ row: r, identity: { isin: String(r.isin), sym: String(r.sym) } }))
    : [{ row: null, identity: { isin: "__SCHEMA_SMOKE__", sym: "__SCHEMA_SMOKE__" } }];
  // Schema smoke must execute the full Details SQL even when today's bounded universe is
  // empty. A non-existent sentinel id returns no domain row while PostgreSQL still parses,
  // plans, and validates every new table, column, alias, lateral join and JSON aggregate.
  const detailIds = selected.length || !schemaSmoke ? selected.map(row => row.id) : [-1];
  const [command, index, journeys, preopenRows, observations, detailRows] = await Promise.all([
    atBuilderStage("ipo-command", () => buildCommand(sql)),
    atBuilderStage("ipo-index", () => buildIpoIndex(sql)),
    Promise.all(journeyQueries.map(({ row, identity }) => limit(async () => ({ row, candles: await atBuilderStage(
      row ? `journey:${String(row.isin)}` : "journey:schema-probe",
      () => fetchJourneyCandles(sql, identity),
    ) })))),
    atBuilderStage("live-preopen", () => fetchPreopenRows(sql)),
    atBuilderStage("preopen-observations", () => sql`SELECT DISTINCT ON (o.ipo_id) o.ipo_id,o.ltp,o.buy_qty,o.sell_qty,o.payload,o.observed_at FROM listing_observations o WHERE o.obs_type='preopen' ORDER BY o.ipo_id,o.observed_at DESC`),
    atBuilderStage("ipo-details", () => fetchDetailsRows(sql, detailIds)),
  ]);
  const latest = new Map(observations.map(o => [String(o.ipo_id), o]));
  const now = new Date().toISOString();
  const globals = [
    { name: "ipo-command:v6", payload: command }, { name: "ipo:index:v3", payload: index },
    { name: "ipo-live-preopen:v2", payload: { ok:true, window:"listing_date = IST-today", book_live:false, live_overlay:"BLOCKED", degraded:"Kite credential automation is not proven safe", count:preopenRows.length, listings:preopenRows.map(r => ({...scoreListing(r),latest_observation:latest.get(String(r.ipo_id))??null})), fetchedAt:now } },
    ...journeys.filter(({ row }) => row !== null).map(({row,candles}) => ({ name:`journey:isin:${String(row!.isin).toUpperCase()}:v1`, payload:{ isin:row!.isin,sym:row!.sym,rows:candles,generated_at:now } })),
  ];
  const details = detailRows.map(row => ({ name:`ipo-details:isin:${String(row.isin).toUpperCase()}:v1`, payload:detailsFromRow(row,now) }));
  return { globals, details };
}

async function publishBatch(endpoint:string,key:string,snapshots:Array<{name:string,payload:unknown}>, label:string) {
  const response=await fetch(endpoint,{method:"POST",headers:{"content-type":"application/json","x-aac-key":key},body:JSON.stringify({snapshots})});
  if(!response.ok) throw new Error(`${label} publication failed ${response.status}: ${await response.text()}`);
  console.log(await response.text());
}

function fixtureSqlClient(): SqlClient {
  let queryCount = 0;
  return (async (strings: TemplateStringsArray) => {
    const query = strings.join("?");
    queryCount += 1;
    // This fixture executes every real snapshot query. Keep the guard here rather
    // than source-grepping so interpolated tagged-template SQL is also checked.
    if (/\bi\.name\b/i.test(query)) throw new Error(`stale ipo identity column in fixture query #${queryCount}: i.name`);
    if (/SELECT DISTINCT i\.id/.test(query)
        && !/i\.listing_date >= \(\s*\(now\(\) AT TIME ZONE 'Asia\/Kolkata'\)::date\s*- \(\?::int\)\s*\)/.test(query)) {
      throw new Error("Journey monitoring-days SQL parameter must be explicitly cast to int");
    }
    if (process.env.SNAPSHOT_TEST_POSTGRES_ERROR === "1" && /SELECT DISTINCT i\.id/.test(query)) {
      throw new Error("column i.forced_missing does not exist");
    }
    if (/COALESCE\(\(SELECT json_agg/.test(query)) return [{ ipo_id:1, isin:"INE000000001", sym:"FIXTURE", company_name:"Fixture IPO", issue_price:100, band_lo:95, band_hi:100, issue_size_cr:500, score:2.5, score_band:"STRONG", engine_version:"v2-score-2", valuation_computed_at:"2026-08-06T00:00:00Z", pe:20, pb:2, pe_source:"rhp_computed:price/eps_post", pb_source:"proxy:issue_size/net_worth", fair_value_lo:110, fair_value_hi:125, inputs_used:{pe_source:"rhp_computed:price/eps_post",pb_source:"proxy:issue_size/net_worth"}, missing_inputs:[], findings:{litigation:["No material litigation"]}, analysis_model:"fixture-model", analysis_prompt_version:"v2-full", analysis_confidence:.9, analyzed_at:"2026-08-06T00:00:00Z", red_flag_count:0, junk_signals:[], fundamental_verdict:"GOOD", decision_reasons:["complete"], decision_evidence:{score_band:"STRONG"}, decided_at:"2026-08-06T00:00:00Z", verified_evidence:[{excerpt:"Verified fixture excerpt",page_number:12,doc_id:1,document:{doc_type:"rhp",url:"https://example.test/rhp.pdf",sha256:"abc",page_count:100},category:"risk",direction:"neutral",source_type:"RHP"}] }];
    if (/SELECT DISTINCT i\.id/.test(query)) return [{ id: 1, isin: "INE000000001", sym: "FIXTURE", listing_date: null, company_name: "Fixture IPO", reason_selected: "fixture" }];
    if (/SELECT i\.id AS ipo_id/.test(query) && !/WHERE i\.listing_date = \(NOW/.test(query)) return [{ ipo_id: 1, sym: "FIXTURE", company_name: "Fixture IPO" }];
    if (/SELECT name_display AS company_name/.test(query)) return [{ sym: "FIXTURE", isin: "INE000000001", company_name: "Fixture IPO" }];
    return [];
  }) as SqlClient;
}

export async function main() {
  const maxIpos = Math.max(PIPELINE_LIMITS.MIN_POSITIVE_LIMIT, Math.min(PIPELINE_LIMITS.SNAPSHOT_HARD_MAX_IPOS, Number(arg("limit", process.env.SNAPSHOT_MAX_IPOS || String(PIPELINE_LIMITS.SNAPSHOT_DEFAULT_IPOS)))));
  const concurrency = Math.max(PIPELINE_LIMITS.MIN_POSITIVE_LIMIT, Math.min(PIPELINE_LIMITS.SNAPSHOT_HARD_MAX_CONCURRENCY, Number(arg("concurrency", String(PIPELINE_LIMITS.SNAPSHOT_DEFAULT_CONCURRENCY)))));
  const dryRun = process.argv.includes("--dry-run");
  const schemaSmoke = process.argv.includes("--schema-smoke");
  if (schemaSmoke && process.env.SNAPSHOT_TEST_FIXTURE === "1") throw new Error("schema smoke requires real Neon SQL; fixture is not allowed");
  const publishEndpoint = schemaSmoke ? null : snapshotPublishEndpoint(process.env.SNAPSHOT_PUBLISH_URL);
  const key = schemaSmoke ? null : requirePublishKey();

  const fixture = process.env.SNAPSHOT_TEST_FIXTURE === "1";
  const realSql = fixture ? null : neon(requireDatabaseUrl(schemaSmoke)) as unknown as SqlClient;
  const sql = fixture ? fixtureSqlClient() : schemaSmoke ? readOnlySqlClient(realSql!) : realSql!;
  const { globals, details } = await buildSnapshots(sql, maxIpos, concurrency, schemaSmoke);
  if (fixture) console.log(JSON.stringify({ snapshot_fixture_sql_verified: true }));
  if (schemaSmoke) {
    console.log(JSON.stringify({ stage: "schema-smoke", domain: "snapshot-builder", selected_count: globals.filter(s => s.name.startsWith("journey:")).length, details_query_count:1, status: "success" }));
    return;
  }

  const { measured, report }=measureDetailsPayloads(details);
  console.log(JSON.stringify({details_payload_measurement:report,configured_max_bytes:PIPELINE_LIMITS.DETAILS_MAX_PAYLOAD_BYTES,details_query_count:1}));
  assertDetailsPayloadSizes(measured,PIPELINE_LIMITS.DETAILS_MAX_PAYLOAD_BYTES);
  if (dryRun) return;
  console.log(JSON.stringify({ payload_bytes:Buffer.byteLength(JSON.stringify({snapshots:globals})), snapshots:globals.length, publish_endpoint: publishEndpoint }));
  await publishBatch(publishEndpoint!,key!,globals,"global/Journey");
  for(let offset=0;offset<details.length;offset+=PIPELINE_LIMITS.DETAILS_PUBLICATION_BATCH_SIZE){
    const batch=details.slice(offset,offset+PIPELINE_LIMITS.DETAILS_PUBLICATION_BATCH_SIZE); const number=Math.floor(offset/PIPELINE_LIMITS.DETAILS_PUBLICATION_BATCH_SIZE)+1;
    try { await publishBatch(publishEndpoint!,key!,batch,`details batch ${number}`); }
    catch(error){ const failingIsins=batch.map(x=>x.name.split(":")[2]); console.error(JSON.stringify({stage:"details-publication",details_batch:number,failing_isins:failingIsins,error:error instanceof Error?error.message:String(error)})); throw error; }
  }
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : String(err));
  process.exit(1);
});
