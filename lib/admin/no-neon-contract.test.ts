// lib/admin/no-neon-contract.test.ts — zero-wake guard (334-1).
// Proves the Admin Operations overview never calls the Neon-backed admin routes
// and never sets up interval polling, so the deployed web app cannot become a
// recurring Neon wake source. A static source check is deliberate: it fails the
// build the moment someone reintroduces a Neon fetch or a timer, without needing
// a browser.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const OVERVIEW = resolve(HERE, "../../app/dashboard/admin/OperationsOverview.tsx");
const src = readFileSync(OVERVIEW, "utf8");

// Strip line comments so the prose ("...are NOT called here") can name the
// routes without tripping the guard; we only care about real code references.
const code = src
  .split("\n")
  .map((l) => l.replace(/\/\/.*$/, ""))
  .join("\n")
  .replace(/\/\*[\s\S]*?\*\//g, "");

const NEON_ROUTES = ["/api/admin/pipeline-steps", "/api/admin/pipeline-failures"];

for (const route of NEON_ROUTES) {
  test(`overview never fetches Neon-backed route ${route}`, () => {
    assert.ok(!code.includes(route), `OperationsOverview must not reference ${route}`);
  });
}

test("overview does not set up interval polling", () => {
  assert.ok(!/setInterval\s*\(/.test(code), "OperationsOverview must not use setInterval (no timer polling)");
});

test("overview only fetches the KV-backed /api/ipo-command", () => {
  const fetches = [...code.matchAll(/fetch\(\s*([A-Za-z0-9_]+|["'`][^"'`]+["'`])/g)].map((m) => m[1]);
  // The only fetch target is the COMMAND_URL constant (KV snapshot).
  for (const target of fetches) {
    assert.ok(
      target === "COMMAND_URL" || /ipo-command/.test(target),
      `unexpected fetch target in overview: ${target}`,
    );
  }
  // And the KV route is the declared source.
  assert.ok(code.includes("/api/ipo-command"), "overview should read the KV /api/ipo-command snapshot");
});
