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

function kv(): KV | null {
  try {
    return (getCloudflareContext().env as unknown as { CACHE?: KV }).CACHE ?? null;
  } catch {
    return null; // local/Vercel — no cache, query direct
  }
}

const DEFAULT_TTL = 43200; // 12h — pipeline refreshes 2x/day

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
