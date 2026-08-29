// lib/web-plane-db-contract.test.ts — zero-wake boundary.
//
// The deployed web plane may use Cloudflare D1/KV bindings, but it must not import
// external SQL clients or DATABASE_URL-backed helpers. Components never query a DB;
// app routes may call lib/d1, which is the approved Cloudflare binding seam.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve, relative, sep } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "..");

const DB_MARKERS: Array<{ label: string; re: RegExp }> = [
  { label: "@neondatabase/serverless", re: /from\s+["']@neondatabase\/serverless["']/ },
  { label: "@vercel/postgres", re: /from\s+["']@vercel\/postgres["']/ },
  { label: "@/lib/db", re: /from\s+["']@\/lib\/db(?:\/[^"']*)?["']/ },
  { label: "pg / postgres driver", re: /from\s+["'](?:pg|postgres|pg-cloudflare)["']/ },
  { label: "psycopg", re: /\bpsycopg\d?\b/ },
  { label: "DATABASE_URL", re: /process\.env\.[A-Za-z_]*DATABASE_URL/ },
];

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

test("app/** has zero external DB imports", () => {
  const offenders = [...dbImporters("app").entries()].map(([f, m]) => `${f} (${m.join(", ")})`);
  assert.deepEqual(offenders, [], "web plane must use Cloudflare D1/KV bindings only; no Neon/Postgres clients or DATABASE_URL");
});

test("the KV-only consumer routes stay free of any external DB client", () => {
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
    assert.deepEqual(hits, [], `${file} must stay free of external DB clients`);
  }
});
