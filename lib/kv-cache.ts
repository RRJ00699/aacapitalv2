// Cloudflare KV contracts. User-facing reads are deliberately incapable of
// building from Neon: primary -> stale/previous -> controlled unavailable.
import { getCloudflareContext } from "@opennextjs/cloudflare";

export type KV = {
  get: (key: string) => Promise<string | null>;
  put: (key: string, value: string, options?: { expirationTtl?: number }) => Promise<void>;
};

let testStore: KV | null | undefined;

function store(): KV | null {
  if (testStore !== undefined) return testStore;
  try {
    return (getCloudflareContext().env as unknown as { CACHE?: KV }).CACHE ?? null;
  } catch {
    return null;
  }
}

export function kvStore(): KV | null { return store(); }
export function setKvStoreForTests(value: KV | null | undefined): void { testStore = value; }

export type StrictCacheHit = { payload: string; source: "primary" | "stale" };

/** Legacy primary/stale reader. It never accepts a builder and therefore cannot wake Neon. */
export async function readStrict(key: string): Promise<StrictCacheHit | null> {
  const kv = store();
  if (!kv) return null;
  try {
    const primary = await kv.get(key);
    if (primary) return { payload: primary, source: "primary" };
    const stale = await kv.get(`${key}:stale`);
    return stale ? { payload: stale, source: "stale" } : null;
  } catch {
    return null;
  }
}

/**
 * Compatibility reader for routes being split into static/live endpoints.
 * The builder argument is intentionally ignored: retaining its type avoids a broad
 * rewrite while making a cold user request structurally unable to execute it.
 */
export async function cached(key: string, _build: () => Promise<unknown>, _ttl?: number): Promise<string> {
  const hit = await readStrict(key);
  if (!hit) throw new Error(`snapshot unavailable: ${key}`);
  return hit.payload;
}

export type SnapshotMetadata = {
  generated_at: string;
  schema_version: string;
  source_freshness: Record<string, string | null>;
  engine_versions: Record<string, string>;
};
export type SnapshotEnvelope = SnapshotMetadata & {
  checksum: string;
  payload: unknown;
};
type Pointer = { version_key: string; checksum: string; generated_at: string };

function stableJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b)).map(([k, v]) => `${JSON.stringify(k)}:${stableJson(v)}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

export async function checksum(value: unknown): Promise<string> {
  const bytes = new TextEncoder().encode(stableJson(value));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, "0")).join("");
}

/** Read active, then retained previous immutable snapshot. Never queries or writes a DB. */
export async function readVersionedSnapshot(baseKey: string): Promise<StrictCacheHit | null> {
  const kv = store();
  if (!kv) return null;
  for (const [pointerKey, source] of [[`${baseKey}:active`, "primary"], [`${baseKey}:previous`, "stale"]] as const) {
    try {
      const rawPointer = await kv.get(pointerKey);
      if (!rawPointer) continue;
      const pointer = JSON.parse(rawPointer) as Pointer;
      const raw = await kv.get(pointer.version_key);
      if (!raw) continue;
      const envelope = JSON.parse(raw) as SnapshotEnvelope;
      if (envelope.checksum !== pointer.checksum || await checksum(envelope.payload) !== envelope.checksum) continue;
      return { payload: JSON.stringify(envelope.payload), source };
    } catch { /* try retained previous */ }
  }
  return null;
}

/** Admin/pipeline-only publication: immutable write, read-back verification, then pointer switch. */
export async function publishVersionedSnapshot(baseKey: string, payload: unknown, metadata: SnapshotMetadata): Promise<Pointer> {
  const kv = store();
  if (!kv) throw new Error("CACHE binding unavailable");
  if (!metadata.generated_at || !metadata.schema_version) throw new Error("invalid snapshot metadata");
  const sum = await checksum(payload);
  const versionKey = `${baseKey}:version:${metadata.generated_at.replace(/[^0-9A-Za-z]/g, "-")}:${sum.slice(0, 16)}`;
  const envelope: SnapshotEnvelope = { ...metadata, checksum: sum, payload };
  await kv.put(versionKey, JSON.stringify(envelope));
  const readBack = await kv.get(versionKey);
  if (!readBack) throw new Error("snapshot read-back failed");
  const verified = JSON.parse(readBack) as SnapshotEnvelope;
  if (verified.checksum !== sum || await checksum(verified.payload) !== sum) throw new Error("snapshot checksum mismatch");
  const activeKey = `${baseKey}:active`;
  const oldActive = await kv.get(activeKey);
  if (oldActive) await kv.put(`${baseKey}:previous`, oldActive);
  const pointer = { version_key: versionKey, checksum: sum, generated_at: metadata.generated_at };
  await kv.put(activeKey, JSON.stringify(pointer));
  return pointer;
}
