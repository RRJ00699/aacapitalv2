#!/usr/bin/env node
// uat/run-lib-tests.mjs — deterministic, cross-platform discovery for the
// lib TypeScript unit tests. The previous `--test "lib/**/*.test.ts"` relied on
// the shell (or node) expanding the quoted glob, which behaves differently
// across bash / GitHub Linux runners / Windows PowerShell and produced
// "Could not find 'lib/**/*.test.ts'" on CI. Here we expand the glob in JS with
// node:fs and hand node an explicit, sorted file list — identical on every OS.
import { globSync } from "node:fs";
import { spawnSync } from "node:child_process";

const patterns = ["lib/**/*.test.ts", "workers/**/tests/**/*.test.ts"];
const files = patterns.flatMap((p) => globSync(p)).sort();
if (files.length === 0) {
  console.error(`run-lib-tests: no files matched ${patterns.join(", ")}`);
  process.exit(1);
}
console.error(`run-lib-tests: ${files.length} test file(s) across ${patterns.length} pattern(s)`);
const res = spawnSync(process.execPath, ["--import", "tsx", "--test", ...files], {
  stdio: "inherit",
});
process.exit(res.status ?? 1);
