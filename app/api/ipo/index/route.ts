import { kvStore } from "@/lib/kv-cache";
import { readVersionedSnapshot, snapshotResponse } from "@/lib/versioned-snapshot";

export const runtime = "edge";
export async function GET() {
  const store = kvStore();
  return snapshotResponse(store ? await readVersionedSnapshot(store, "ipo:index:v3") : null,
    { rows: [], degraded: "snapshot unavailable" });
}
