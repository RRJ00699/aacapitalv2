// uat/serve.mjs — boots the PRODUCTION build in fixture mode (zero Neon, zero
// paid APIs) and rewrites __TODAY__ in the seed to the real IST date so
// LISTING-stage journeys are deterministic on any day.
import { readFileSync, writeFileSync, mkdtempSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";
import { spawn } from "child_process";
import { createRequire } from "module";
const ist = new Date(Date.now() + 5.5 * 3600_000).toISOString().slice(0, 10);
const seed = readFileSync("uat/fixtures/seed.json", "utf8").replaceAll("__TODAY__", ist);
const dir = mkdtempSync(join(tmpdir(), "aac-uat-"));
const fixture = join(dir, "seed.json");
writeFileSync(fixture, seed);
const snapshots = readFileSync("uat/fixtures/snapshots.json", "utf8").replaceAll("__TODAY__", ist);
const snapshotFixture = join(dir, "snapshots.json");
writeFileSync(snapshotFixture, snapshots);
const nextCli = createRequire(import.meta.url).resolve("next/dist/bin/next");
const child = spawn(process.execPath, [nextCli, "start", "-p", String(process.env.UAT_PORT || 4123)], {
  stdio: "inherit",
  env: { ...process.env, UAT_FIXTURE_JSON: fixture, UAT_SNAPSHOT_JSON: snapshotFixture,
    DATABASE_URL: "postgres://uat:uat@fixture.invalid/uat",
    AUTH_SECRET: "uat-fixture-secret-not-production", NEXTAUTH_SECRET: "uat-fixture-secret-not-production",
    NEXTAUTH_URL: `http://localhost:${process.env.UAT_PORT || 4123}` },
});
child.on("error", (error) => {
  console.error(`[uat] unable to start the repository-local Next.js CLI: ${error.code || error.name}. Ensure Node dependencies are installed.`);
  process.exit(1);
});
child.on("exit", (c) => process.exit(c ?? 0));
