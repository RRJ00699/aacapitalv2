// Route-harness stubs. Discipline: the Neon stub COUNTS every query and never
// touches the network; anything unstubbed that tries to leave the process
// should throw, not silently succeed.
globalThis.__H = globalThis.__H ?? { queries: [], kv: new Map(), kvGets: 0, kvPuts: 0 };

// ---- '@neondatabase/serverless' ----
export function neon(_url) {
  const tag = (strings, ...vals) => {
    const q = strings.join("$?");
    globalThis.__H.queries.push(q.trim().slice(0, 120));
    return Promise.resolve(rowsFor(q));
  };
  tag.transaction = async (fn) => fn(tag);
  return tag;
}
export const neonConfig = {};
export class Pool {
  constructor() { throw new Error("route-harness: Pool (websocket) not stubbed — a route tried a real connection"); }
}

// minimal shaped rows so handlers that read [0].x don't crash
function rowsFor(q) {
  const lower = q.toLowerCase();
  if (lower.includes("count(*)")) return [{ above: 60, total: 100, count: 0 }];
  if (lower.includes("max(date)")) return [{ d: null }];
  return [];
}

// ---- '@/lib/api-guard' ----
export async function requireUser() { return null; }        // authorized
export async function requireAdmin() { return null; }

// ---- '@opennextjs/cloudflare' ----
export function getCloudflareContext() {
  return {
    env: {
      CACHE: {
        get: async (k) => { globalThis.__H.kvGets++; return globalThis.__H.kv.get(k) ?? null; },
        put: async (k, v, _o) => { globalThis.__H.kvPuts++; globalThis.__H.kv.set(k, v); },
      },
    },
  };
}
