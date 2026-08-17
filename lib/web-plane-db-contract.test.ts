// lib/web-plane-db-contract.test.ts — the zero-wake boundary, frozen.
//
// The web plane (app/** + components/**) is meant to be a KV-only consumer of
// pipeline-published snapshots. This test is the guard on that boundary:
//
//   1. components/** may NEVER import a database client. No allowlist, no
//      exceptions — a component that queries is a design error, not a backlog
//      item.
//   2. app/** must match the frozen allowlist below EXACTLY. A new file with a
//      DB import fails (the list cannot grow by accident); a route that is
//      genuinely converted to KV must be deleted from the list in the same
//      commit (the list can only shrink deliberately).
//
// Every allowlisted entry names WHY it still holds a DB client and the exact
// producer contract that would let it become a KV consumer, so the list reads
// as the remaining zero-wake work rather than as permission to stay.
//
// NOTE on the entries pinned by `_scripts/tests/test_route_runtime.py`: that
// suite asserts a NON-ZERO query count for several of these routes
// (`QUERY_CEILING`'s `assert q == ceiling or q > 0`, and
// `test_A2_market_snapshot_second_call_zero_queries`'s `c1["queries"] > 0`).
// Converting those routes therefore requires moving those pins in the same
// change, and `_scripts/**` is Codex-owned. The blocked ones are marked below.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve, relative, sep } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "..");

type Allowed = { reason: string; contract: string };

/** Files under app/** that still carry a DB client, and what would free them. */
const ALLOWED_DB_IMPORTS: Record<string, Allowed> = {
  "app/api/access-note/route.ts": {
    reason: "Public WRITE path: attaches a note to the newest pending access_requests row.",
    contract: "None possible as a consumer — a write needs a writable store. Convert only if access requests move off Postgres.",
  },
  "app/api/admin/access/route.ts": {
    reason: "Admin READ + WRITE of access_requests (approve/deny).",
    contract: "None possible as a consumer — approvals are writes.",
  },
  "app/api/admin/diagnostics/route.ts": {
    reason: "Whitelisted, on-demand admin diagnostics against canonical tables.",
    contract: "Would need a published diagnostics snapshot; on-demand freshness is the point, so KV would defeat it.",
  },
  "app/api/admin/jobs/route.ts": {
    reason: "Admin job runner: reads job_runs and enqueues rows on Run.",
    contract: "None possible as a consumer — enqueueing is a write.",
  },
  "app/api/admin/pipeline-failures/route.ts": {
    reason: "Settings 'Pipeline health' panel: 7-day pipeline_failures window.",
    contract: "B-2 pipeline-health:v1 (KV). BLOCKED additionally by the QUERY_CEILING pin of 1 in _scripts/tests/test_route_runtime.py.",
  },
  "app/api/admin/pipeline-steps/route.ts": {
    reason: "Settings step board for the latest pipeline run.",
    contract: "B-2 pipeline-health:v1 (KV). BLOCKED additionally by the QUERY_CEILING pin of 1 in _scripts/tests/test_route_runtime.py.",
  },
  "app/api/admin/secrets/route.ts": {
    reason: "Admin secret presence/rotation state; POST writes.",
    contract: "None possible as a consumer — secrets must not be mirrored into KV.",
  },
  "app/api/auth/zerodha/callback/route.ts": {
    reason: "Broker OAuth callback persists the Kite session.",
    contract: "None possible as a consumer — session persistence is a write.",
  },
  "app/api/auth/zerodha/status/route.ts": {
    reason: "Reads the stored Kite session to report connection state.",
    contract: "Would need a published broker-session-state key; token state must not be cached beyond its TTL.",
  },
  "app/api/ipo/cum-volume/route.ts": {
    reason: "10:29–11:00 IST cumulative-volume confirmation from ipo_tick_feed, KV-cached (24h once final, 60s in-window).",
    contract: "B-4 — publish the listing-day cumulative-volume window to KV so the tile is a pure consumer.",
  },
  "app/api/ipo/tick-feed/route.ts": {
    reason: "Live latest tick is already KV-only; the expanded chart's history series still reads ipo_tick_feed.",
    contract: "B-5 — publish the listing-day tick series to KV so the chart is a pure consumer.",
  },
  "app/api/market/global/route.ts": {
    reason: "Yahoo + Zerodha are the live sources; Neon supplies the India snapshot fallback, FII/DII flows, breadth and the after-hours global_cache (and writes it).",
    contract: "B-6 market-india:v1 (KV). BLOCKED additionally by the QUERY_CEILING pin of 5 in _scripts/tests/test_route_runtime.py.",
  },
  "app/api/market/snapshot/route.ts": {
    reason: "Dashboard market tiles: regime, breadth, PCR, deploy band and flows come from market_snapshot / market_regimes.",
    contract: "B-6 market-india:v1 (KV). BLOCKED additionally by test_A2_market_snapshot_second_call_zero_queries, which asserts the first call DOES query.",
  },
  "app/api/settings/route.ts": {
    reason: "User preference key/value store in Neon. No UI consumer currently fetches it.",
    contract: "None as a consumer — preferences are writes. BLOCKED additionally by the QUERY_CEILING pin of 2 in _scripts/tests/test_route_runtime.py.",
  },
};

const DB_MARKERS: Array<{ label: string; re: RegExp }> = [
  { label: "@neondatabase/serverless", re: /from\s+["']@neondatabase\/serverless["']/ },
  { label: "@vercel/postgres", re: /from\s+["']@vercel\/postgres["']/ },
  { label: "@/lib/db", re: /from\s+["']@\/lib\/db(?:\/[^"']*)?["']/ },
  { label: "pg / postgres driver", re: /from\s+["'](?:pg|postgres|pg-cloudflare)["']/ },
  { label: "psycopg", re: /\bpsycopg\d?\b/ },
  { label: "DATABASE_URL", re: /process\.env\.[A-Za-z_]*DATABASE_URL/ },
];

/** Comments are prose, not code: a file may NAME a driver without importing it. */
function codeOf(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .map((line) => line.replace(/(^|[^:])\/\/.*$/, "$1"))
    .join("\n");
}

function walk(dir: string, out: string[] = []): string[] {
  if (!existsSync(dir)) return out;
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry.startsWith(".")) continue;
    const full = resolve(dir, entry);
    if (statSync(full).isDirectory()) walk(full, out);
    else if (/\.tsx?$/.test(entry) && !/\.test\.tsx?$/.test(entry)) out.push(full);
  }
  return out;
}

/** Every scanned file that really imports a DB client, as a repo-relative path. */
function dbImporters(dir: string): Map<string, string[]> {
  const found = new Map<string, string[]>();
  for (const file of walk(resolve(ROOT, dir))) {
    const code = codeOf(readFileSync(file, "utf8"));
    const hits = DB_MARKERS.filter((m) => m.re.test(code)).map((m) => m.label);
    if (hits.length) found.set(relative(ROOT, file).split(sep).join("/"), hits);
  }
  return found;
}

test("components/** never imports a database client", () => {
  const offenders = [...dbImporters("components").entries()].map(([f, m]) => `${f} (${m.join(", ")})`);
  assert.deepEqual(offenders, [], "a component must consume an API/KV payload, never a database");
});

test("app/** DB imports match the frozen allowlist exactly", () => {
  const actual = [...dbImporters("app").keys()].sort();
  const allowed = Object.keys(ALLOWED_DB_IMPORTS).sort();
  const added = actual.filter((f) => !allowed.includes(f));
  const converted = allowed.filter((f) => !actual.includes(f));
  assert.deepEqual(added, [], "new DB import in the web plane — convert it to a KV consumer or justify it in ALLOWED_DB_IMPORTS");
  assert.deepEqual(converted, [], "these no longer import a DB — remove them from ALLOWED_DB_IMPORTS so the list keeps shrinking");
});

test("every allowlisted file still exists and names the contract that would free it", () => {
  for (const [file, entry] of Object.entries(ALLOWED_DB_IMPORTS)) {
    assert.ok(existsSync(resolve(ROOT, file)), `allowlist is stale — ${file} no longer exists`);
    assert.ok(entry.reason.trim().length > 20, `${file}: allowlist entry needs a real reason`);
    assert.ok(entry.contract.trim().length > 20, `${file}: allowlist entry must name the producer contract (or say why none applies)`);
  }
});

test("the KV-only consumer routes stay free of any DB client", () => {
  // The snapshot consumers are the load-bearing zero-wake routes: every IPO
  // page load goes through them. They must never regain a database import.
  const kvOnly = [
    "app/api/ipo-command/route.ts",
    "app/api/ipo/index/route.ts",
    "app/api/ipo/journey/route.ts",
    "app/api/ipo/details/[isin]/route.ts",
    "app/api/ipo/live-preopen/route.ts",
    "app/api/ipo/monitor/route.ts",
  ];
  for (const file of kvOnly) {
    const full = resolve(ROOT, file);
    assert.ok(existsSync(full), `KV-only route missing: ${file}`);
    const hits = DB_MARKERS.filter((m) => m.re.test(codeOf(readFileSync(full, "utf8")))).map((m) => m.label);
    assert.deepEqual(hits, [], `${file} must stay KV-only`);
    assert.equal(ALLOWED_DB_IMPORTS[file], undefined, `${file} must never be allowlisted`);
  }
});
