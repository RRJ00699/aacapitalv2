import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import test from "node:test";

const mainWorkerRoutes = [
  "app/api/ipo-command/route.ts",
  "app/api/ipo/index/route.ts",
  "app/api/ipo/journey/route.ts",
  "app/api/ipo/live-preopen/route.ts",
] as const;

test("main OpenNext Worker routes do not opt into the unsupported Edge runtime", () => {
  const routes = readdirSync("app", { recursive: true, encoding: "utf8" })
    .filter((path) => path.endsWith("/route.ts"))
    .map((path) => `app/${path}`);

  for (const route of routes) {
    const source = readFileSync(route, "utf8");
    assert.doesNotMatch(source, /export\s+const\s+runtime\s*=\s*["']edge["']/,
      `${route} must run in the main OpenNext Worker`);
  }
});

test("KV snapshot routes do not import Neon or database clients", () => {
  for (const route of mainWorkerRoutes) {
    const source = readFileSync(route, "utf8");
    assert.doesNotMatch(source, /(?:from|import\s*)\s*["'](?:@neondatabase\/|@\/lib\/(?:db|database))[^"']*["']/,
      `${route} must remain a zero-Neon snapshot consumer`);
  }
});
