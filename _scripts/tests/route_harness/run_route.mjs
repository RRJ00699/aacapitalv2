// Usage: node run_route.mjs <route.ts path> <calls>
// Bundles the route with Neon/auth/Cloudflare aliased to stubs.mjs, invokes
// GET <calls> times against one shared module instance (same isolate, like a
// warm worker), prints JSON: per-call query counts, kv stats, statuses.
import { build } from "esbuild";
import { pathToFileURL, fileURLToPath } from "node:url";
import path from "node:path";
import fs from "node:fs";
import os from "node:os";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "../../..");
const routeFile = path.resolve(ROOT, process.argv[2]);
const calls = Number(process.argv[3] || 2);
// Optional: "<key>@<callNo>" — delete that KV key just before call N, simulating
// a primary-TTL lapse so tests can prove the stale-tier path (Phase-2).
const expireArg = process.argv[4] || "";
const STUBS = path.join(HERE, "stubs.mjs");

const stubPlugin = {
  name: "stubs",
  setup(b) {
    const hijack = [
      /^@neondatabase\/serverless$/, /^@\/lib\/api-guard$/,
      /^@opennextjs\/cloudflare$/, /^pg$/, /^postgres$/, /^next\/headers$/,
    ];
    b.onResolve({ filter: /.*/ }, (args) => {
      if (hijack.some((re) => re.test(args.path))) return { path: STUBS };
      if (args.path.startsWith("@/")) return { path: path.join(ROOT, args.path.slice(2)) + guessExt(path.join(ROOT, args.path.slice(2))) };
      return undefined;
    });
  },
};
function guessExt(p) {
  for (const e of ["", ".ts", ".tsx", "/index.ts"]) {
    const c = p + e;
    if (fs.existsSync(c) && (e !== "" || fs.statSync(c).isFile())) return e;
  }
  return ".ts";
}

const out = path.join(os.tmpdir(), `route_${Date.now()}_${Math.random().toString(36).slice(2)}.mjs`);
await build({
  entryPoints: [routeFile], bundle: true, format: "esm", platform: "node",
  outfile: out, plugins: [stubPlugin], logLevel: "silent",
  banner: { js: [
    "import { createRequire } from 'node:module';",
    "import { fileURLToPath as __fu } from 'node:url';",
    "import { dirname as __dn } from 'node:path';",
    "const require = createRequire(import.meta.url);",
    "const __filename = __fu(import.meta.url);",
    "const __dirname = __dn(__filename);",
  ].join("\n") },
});

process.env.DATABASE_URL = "postgresql://harness-stub-never-connects";
const mod = await import(pathToFileURL(out).href);
const results = [];
for (let i = 0; i < calls; i++) {
  const H = globalThis.__H ?? (globalThis.__H = { queries: [], kv: globalThis.__H?.kv ?? new Map(), kvGets: 0, kvPuts: 0 });
  if (expireArg) {
    const at = expireArg.lastIndexOf("@");
    if (at > 0 && Number(expireArg.slice(at + 1)) === i + 1) H.kv.delete(expireArg.slice(0, at));
  }
  const before = H.queries.length, gBefore = H.kvGets, pBefore = H.kvPuts, oBefore = (H.kvOps || (H.kvOps = [])).length;
  const u = "https://x.local/api/" + path.basename(path.dirname(routeFile));
  const req = { url: u, nextUrl: new URL(u),
                headers: { get: (_k) => null, has: () => false } };
  let status = null, xcache = null, err = null, body = null;
  try {
    const res = await mod.GET(req);
    status = res?.status ?? 200;
    xcache = res?.headers?.get ? res.headers.get("x-cache") : null;
    if (process.env.HARNESS_CAPTURE_BODY === "1" && res?.text) {
      try { body = (await res.text()).slice(0, 20000); } catch { body = null; }
    }
  } catch (e) { err = String(e).slice(0, 160); }
  results.push({ call: i + 1, queries: H.queries.length - before,
                 kv_gets: H.kvGets - gBefore, kv_puts: H.kvPuts - pBefore,
                 kv_ops: H.kvOps.slice(oBefore),
                 status, xcache, err, body });
}
console.log(JSON.stringify({ route: process.argv[2], results, sampled_queries: globalThis.__H.queries.slice(0, 3) }));
fs.unlinkSync(out);
