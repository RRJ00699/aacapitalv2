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
const maxIpos = Math.max(PIPELINE_LIMITS.MIN_POSITIVE_LIMIT, Math.min(PIPELINE_LIMITS.SNAPSHOT_HARD_MAX_IPOS, Number(arg("limit", process.env.SNAPSHOT_MAX_IPOS || String(PIPELINE_LIMITS.SNAPSHOT_DEFAULT_IPOS)))));
const concurrency = Math.max(PIPELINE_LIMITS.MIN_POSITIVE_LIMIT, Math.min(PIPELINE_LIMITS.SNAPSHOT_HARD_MAX_CONCURRENCY, Number(arg("concurrency", String(PIPELINE_LIMITS.SNAPSHOT_DEFAULT_CONCURRENCY)))));
const dryRun = process.argv.includes("--dry-run");
const url = process.env.DATABASE_URL || process.env.NEON_DATABASE_URL;
if (!url) throw new Error("DATABASE_URL is required");
const sql = neon(url) as unknown as SqlClient;

const selected = await selectJourneyUniverse(sql, maxIpos);
console.log(JSON.stringify({ selected_count: selected.length, selected_isins: selected.map(r => r.isin), max_ipos: maxIpos,
  concurrency, expected_neon_queries: PIPELINE_LIMITS.SNAPSHOT_FIXED_NEON_QUERIES + selected.length, scope: PIPELINE_SCOPE_DESCRIPTION }));
if (dryRun) process.exit(0);
const limit = pLimit(concurrency);
const [command, index, journeys, preopenRows, observations] = await Promise.all([
  buildCommand(sql), buildIpoIndex(sql),
  Promise.all(selected.map(r => limit(async () => ({ row: r, candles: await fetchJourneyCandles(sql, { isin: String(r.isin), sym: String(r.sym) }) })))),
  fetchPreopenRows(sql),
  sql`SELECT DISTINCT ON (o.ipo_id) o.ipo_id,o.ltp,o.buy_qty,o.sell_qty,o.payload,o.observed_at FROM listing_observations o WHERE o.obs_type='preopen' ORDER BY o.ipo_id,o.observed_at DESC`,
]);
const latest = new Map(observations.map(o => [String(o.ipo_id), o]));
const now = new Date().toISOString();
const snapshots = [
  { name: "ipo-command:v6", payload: command }, { name: "ipo:index:v3", payload: index },
  { name: "ipo-live-preopen:v2", payload: { ok:true, window:"listing_date = IST-today", book_live:false, live_overlay:"BLOCKED", degraded:"Kite credential automation is not proven safe", count:preopenRows.length, listings:preopenRows.map(r => ({...scoreListing(r),latest_observation:latest.get(String(r.ipo_id))??null})), fetchedAt:now } },
  ...journeys.map(({row,candles}) => ({ name:`journey:isin:${String(row.isin).toUpperCase()}:v1`, payload:{ isin:row.isin,sym:row.sym,rows:candles,generated_at:now } })),
];
const payload = JSON.stringify({ snapshots });
console.log(JSON.stringify({ payload_bytes:Buffer.byteLength(payload), snapshots:snapshots.length }));
const publishUrl = process.env.SNAPSHOT_PUBLISH_URL;
const key = process.env.SNAPSHOT_PUBLISH_KEY;
if (!publishUrl?.startsWith("https://") || !key) throw new Error("SNAPSHOT_PUBLISH_URL and SNAPSHOT_PUBLISH_KEY required");
const response = await fetch(`${publishUrl.replace(/\/$/,"")}/api/admin/snapshots`, { method:"POST",headers:{"content-type":"application/json","x-aac-key":key},body:payload });
if (!response.ok) throw new Error(`publication failed ${response.status}: ${await response.text()}`);
console.log(await response.text());
