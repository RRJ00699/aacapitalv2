import { kvStore } from "@/lib/kv-cache";

export type SnapshotSource = "active" | "previous";
export type SnapshotRead = { payload: string; source: SnapshotSource; version: string };
export type SnapshotKV = NonNullable<ReturnType<typeof kvStore>>;

const pointer = (name: string, which: "active" | "previous") => `snapshot:${name}:${which}`;
const dataKey = (name: string, version: string) => `snapshot:${name}:data:${version}`;

/** Atomic-from-the-reader's-point-of-view publication: immutable data first, pointer last. */
export async function publishVersionedSnapshot(
  store: SnapshotKV, name: string, value: unknown, version = new Date().toISOString(),
): Promise<string> {
  const payload = JSON.stringify(value);
  JSON.parse(payload); // refuse non-JSON payloads before touching pointers
  const old = await store.get(pointer(name, "active"));
  await store.put(dataKey(name, version), payload, { expirationTtl: 604800 });
  if (old && old !== version) await store.put(pointer(name, "previous"), old, { expirationTtl: 604800 });
  await store.put(pointer(name, "active"), version, { expirationTtl: 604800 });
  return version;
}

/** Validate active JSON; transparently roll back to the previous immutable version. */
export async function readVersionedSnapshot(store: SnapshotKV, name: string): Promise<SnapshotRead | null> {
  for (const source of ["active", "previous"] as const) {
    const version = await store.get(pointer(name, source));
    if (!version) continue;
    const payload = await store.get(dataKey(name, version));
    if (!payload) continue;
    try { JSON.parse(payload); return { payload, source, version }; } catch { /* try previous */ }
  }
  return null;
}

export function snapshotResponse(hit: SnapshotRead | null, empty: unknown): Response {
  return new Response(hit?.payload ?? JSON.stringify(empty), {
    status: 200,
    headers: {
      "content-type": "application/json",
      "x-cache": hit ? "HIT" : "MISS",
      ...(hit?.source === "previous" ? { "x-snapshot-rollback": "previous" } : {}),
      ...(hit ? { "x-snapshot-version": hit.version } : {}),
    },
  });
}
