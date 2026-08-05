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

function requireDatabaseUrl(): string {
  const url = process.env.DATABASE_URL || process.env.NEON_DATABASE_URL;
  if (!url) throw new Error("DATABASE_URL is required");
  return url;
}

async function buildSnapshots(sql: SqlClient, maxIpos: number, concurrency: number) {
  const selected = await selectJourneyUniverse(sql, maxIpos);
  console.log(JSON.stringify({ selected_count: selected.length, selected_isins: selected.map(r => r.isin), max_ipos: maxIpos,
    concurrency, expected_neon_queries: PIPELINE_LIMITS.SNAPSHOT_FIXED_NEON_QUERIES + selected.length, scope: PIPELINE_SCOPE_DESCRIPTION }));
  const limit = pLimit(concurrency);
  const [command, index, journeys, preopenRows, observations] = await Promise.all([
    buildCommand(sql), buildIpoIndex(sql),
    Promise.all(selected.map(r => limit(async () => ({ row: r, candles: await fetchJourneyCandles(sql, { isin: String(r.isin), sym: String(r.sym) }) })))),
    fetchPreopenRows(sql),
    sql`SELECT DISTINCT ON (o.ipo_id) o.ipo_id,o.ltp,o.buy_qty,o.sell_qty,o.payload,o.observed_at FROM listing_observations o WHERE o.obs_type='preopen' ORDER BY o.ipo_id,o.observed_at DESC`,
  ]);
  const latest = new Map(observations.map(o => [String(o.ipo_id), o]));
  const now = new Date().toISOString();
  return [
    { name: "ipo-command:v6", payload: command }, { name: "ipo:index:v3", payload: index },
    { name: "ipo-live-preopen:v2", payload: { ok:true, window:"listing_date = IST-today", book_live:false, live_overlay:"BLOCKED", degraded:"Kite credential automation is not proven safe", count:preopenRows.length, listings:preopenRows.map(r => ({...scoreListing(r),latest_observation:latest.get(String(r.ipo_id))??null})), fetchedAt:now } },
    ...journeys.map(({row,candles}) => ({ name:`journey:isin:${String(row.isin).toUpperCase()}:v1`, payload:{ isin:row.isin,sym:row.sym,rows:candles,generated_at:now } })),
  ];
}

function fixtureSnapshots() {
  const now = "2026-08-05T00:00:00.000Z";
  return [
    { name: "ipo-command:v6", payload: { cards: [{ sym: "FIXTURE", company_name: "Fixture IPO" }], filtered: [], filtered_count: 0, live: [], levels: [], blocks: [], post: [], brlm: [], dl: [], track: [] } },
    { name: "ipo:index:v3", payload: { ok: true, rows: [{ sym: "FIXTURE", isin: "INE000000001" }], generated_at: now } },
    { name: "ipo-live-preopen:v2", payload: { ok: true, window: "listing_date = IST-today", book_live: false, live_overlay: "BLOCKED", count: 1, listings: [{ sym: "FIXTURE", verdict: "WATCH" }], fetchedAt: now } },
    { name: "journey:isin:INE000000001:v1", payload: { isin: "INE000000001", sym: "FIXTURE", rows: [], generated_at: now } },
  ];
}

export async function main() {
  const maxIpos = Math.max(PIPELINE_LIMITS.MIN_POSITIVE_LIMIT, Math.min(PIPELINE_LIMITS.SNAPSHOT_HARD_MAX_IPOS, Number(arg("limit", process.env.SNAPSHOT_MAX_IPOS || String(PIPELINE_LIMITS.SNAPSHOT_DEFAULT_IPOS)))));
  const concurrency = Math.max(PIPELINE_LIMITS.MIN_POSITIVE_LIMIT, Math.min(PIPELINE_LIMITS.SNAPSHOT_HARD_MAX_CONCURRENCY, Number(arg("concurrency", String(PIPELINE_LIMITS.SNAPSHOT_DEFAULT_CONCURRENCY)))));
  const dryRun = process.argv.includes("--dry-run");
  const publishEndpoint = snapshotPublishEndpoint(process.env.SNAPSHOT_PUBLISH_URL);
  const key = requirePublishKey();

  const snapshots = process.env.SNAPSHOT_TEST_FIXTURE === "1"
    ? fixtureSnapshots()
    : await buildSnapshots(neon(requireDatabaseUrl()) as unknown as SqlClient, maxIpos, concurrency);

  if (dryRun) return;
  const payload = JSON.stringify({ snapshots });
  console.log(JSON.stringify({ payload_bytes:Buffer.byteLength(payload), snapshots:snapshots.length, publish_endpoint: publishEndpoint }));
  const response = await fetch(publishEndpoint, { method:"POST",headers:{"content-type":"application/json","x-aac-key":key},body:payload });
  if (!response.ok) throw new Error(`publication failed ${response.status}: ${await response.text()}`);
  console.log(await response.text());
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : String(err));
  process.exit(1);
});
