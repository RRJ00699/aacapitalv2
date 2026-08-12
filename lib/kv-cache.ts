// lib/kv-cache.ts — shared read-cache helper (asset-light Step 2).
// Any GET route that serves pipeline-derived data wraps its DB work in
// cached(): serves from KV when warm, queries + writes KV on miss. The
// pipeline warms these keys post-run (like ipo-command), so Neon sees zero
// read traffic between the 2x/day pipelines.
import { getCloudflareContext } from "@opennextjs/cloudflare";

type KV = {
  get: (k: string) => Promise<string | null>;
  put: (k: string, v: string, o?: { expirationTtl?: number }) => Promise<void>;
};

let testKV: KV | null | undefined;
export function __setTestKVForIntegration(store: KV | null | undefined): void {
  if (process.env.NODE_ENV === "production") throw new Error("test KV injection is disabled in production");
  testKV = store;
}

function kv(): KV | null {
  if (testKV !== undefined) return testKV;
  const fixturePath = process.env.UAT_SNAPSHOT_JSON;
  if (fixturePath) {
    // The browser UAT boots the production build without a Cloudflare binding.
    // Give that build a read-only, file-backed versioned-snapshot store so the
    // same KV-only routes are exercised with deterministic data. This variable
    // is set only by uat/serve.mjs; production never receives it.
    const readFixture = () => {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      return JSON.parse(require("fs").readFileSync(fixturePath, "utf8")) as Record<string, unknown>;
    };
    return {
      async get(key: string) {
        const active = key.match(/^snapshot:(.+):active$/);
        if (active) return Object.hasOwn(readFixture(), active[1]) ? "uat-fixture" : null;
        const data = key.match(/^snapshot:(.+):data:uat-fixture$/);
        if (data) {
          const value = readFixture()[data[1]];
          return value === undefined ? null : JSON.stringify(value);
        }
        return null;
      },
      async put() { /* UAT fixture is intentionally read-only. */ },
    };
  }
  try {
    return (getCloudflareContext().env as unknown as { CACHE?: KV }).CACHE ?? null;
  } catch {
    return null; // local/Vercel — no cache, query direct
  }
}

const DEFAULT_TTL = 43200; // 12h — pipeline refreshes 2x/day

/** Exposed for routes needing conditional TTLs (e.g. cum-volume). */
export function kvStore(): KV | null { return kv(); }

/** Serve `key` from KV if present; else run `build()`, cache it, return it. */
export async function cached(
  key: string,
  build: () => Promise<unknown>,
  ttl: number = DEFAULT_TTL,
): Promise<string> {
  const store = kv();
  if (store) {
    try {
      const hit = await store.get(key);
      if (hit) return hit;
    } catch { /* fall through to build */ }
  }
  const payload = JSON.stringify(await build());
  if (store) {
    try { await store.put(key, payload, { expirationTtl: ttl }); } catch { /* best-effort */ }
  }
  return payload;
}

// ── Phase-2 zero-idle: stale tier ───────────────────────────────────────────
// For pipeline-warmed keys (ipo-command): a primary-TTL miss must NOT wake
// Neon during market hours. Every write keeps a long-lived `${key}:stale`
// twin; on primary miss we serve the twin (flagged) and leave the DB asleep.
// Only a true cold start (neither key) falls through to build().
export type StaleCacheHit = { payload: string; source: "kv" | "stale" | "build" };
const STALE_TTL = 604800; // 7d — pipeline runs 2x/day; 7d of misses = alarms elsewhere

export async function kvPutBoth(
  key: string, payload: string,
  ttl: number = DEFAULT_TTL, staleTtl: number = STALE_TTL,
): Promise<void> {
  const store = kv();
  if (!store) return;
  try { await store.put(key, payload, { expirationTtl: ttl }); } catch { /* best-effort */ }
  try { await store.put(`${key}:stale`, payload, { expirationTtl: staleTtl }); } catch { /* best-effort */ }
}

export async function cachedWithStale(
  key: string,
  build: () => Promise<unknown>,
  ttl: number = DEFAULT_TTL, staleTtl: number = STALE_TTL,
): Promise<StaleCacheHit> {
  const store = kv();
  if (store) {
    try {
      const hit = await store.get(key);
      if (hit) return { payload: hit, source: "kv" };
      const stale = await store.get(`${key}:stale`);
      if (stale) return { payload: stale, source: "stale" }; // Neon stays asleep
    } catch { /* fall through to build */ }
  }
  const payload = JSON.stringify(await build());
  await kvPutBoth(key, payload, ttl, staleTtl);
  return { payload, source: "build" };
}
