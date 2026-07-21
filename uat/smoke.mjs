// npm run uat:smoke -- --base-url=https://... (PowerShell-safe passthrough)
import { spawnSync } from "child_process";
const arg = process.argv.find((a) => a.startsWith("--base-url="));
const url = arg ? arg.split("=")[1] : process.env.UAT_BASE_URL;
if (!url) { console.error("usage: npm run uat:smoke -- --base-url=<URL>"); process.exit(2); }
const r = spawnSync("npx", ["playwright", "test", "uat/tests/smoke.spec.ts", "--project=desktop"],
  { stdio: "inherit", env: { ...process.env, UAT_BASE_URL: url } });
process.exit(r.status ?? 1);
