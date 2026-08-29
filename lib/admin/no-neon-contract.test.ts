// lib/admin/no-neon-contract.test.ts — zero-wake guard.
// The Operations overview must stay timer-free and fetch only the published
// command snapshot. Admin diagnostic/health routes are now D1-backed, so their
// mere existence is no longer a Neon-wake violation.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const OVERVIEW = resolve(HERE, "../../app/dashboard/admin/OperationsOverview.tsx");
const src = readFileSync(OVERVIEW, "utf8");

const code = src
  .split("\n")
  .map((l) => l.replace(/\/\/.*$/, ""))
  .join("\n")
  .replace(/\/\*[\s\S]*?\*\//g, "");

test("overview does not set up interval polling", () => {
  assert.ok(!/setInterval\s*\(/.test(code), "OperationsOverview must not use setInterval (no timer polling)");
});

test("overview only fetches the KV-backed /api/ipo-command", () => {
  const fetches = [...code.matchAll(/fetch\(\s*([A-Za-z0-9_]+|["'`][^"'`]+["'`])/g)].map((m) => m[1]);
  for (const target of fetches) {
    assert.ok(
      target === "COMMAND_URL" || /ipo-command/.test(target),
      `unexpected fetch target in overview: ${target}`,
    );
  }
  assert.ok(code.includes("/api/ipo-command"), "overview should read the KV /api/ipo-command snapshot");
});
