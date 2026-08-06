// uat/serve.mjs — boots the PRODUCTION build in fixture mode (zero Neon, zero
// paid APIs) and rewrites __TODAY__ in the seed to the real IST date so
// LISTING-stage journeys are deterministic on any day.
import { readFileSync, writeFileSync, mkdtempSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";
import { spawn } from "child_process";
const ist = new Date(Date.now() + 5.5 * 3600_000).toISOString().slice(0, 10);
const seed = readFileSync("uat/fixtures/seed.json", "utf8").replaceAll("__TODAY__", ist);
const dir = mkdtempSync(join(tmpdir(), "aac-uat-"));
const fixture = join(dir, "seed.json");
writeFileSync(fixture, seed);
const npx = process.platform === "win32" ? "npx.cmd" : "npx";
const child = spawn(npx, ["next", "start", "-p", String(process.env.UAT_PORT || 4123)], {
  stdio: "inherit",
  env: { ...process.env, UAT_FIXTURE_JSON: fixture,
    DATABASE_URL: "postgres://uat:uat@fixture.invalid/uat",
    AUTH_SECRET: "uat-fixture-secret-not-production", NEXTAUTH_SECRET: "uat-fixture-secret-not-production",
    NEXTAUTH_URL: `http://localhost:${process.env.UAT_PORT || 4123}` },
});
child.on("error", (error) => {
  console.error(`[uat] unable to start Next.js via ${npx}: ${error.code || error.name}. Ensure Node dependencies are installed and npm is on PATH.`);
  process.exit(1);
});
child.on("exit", (c) => process.exit(c ?? 0));
