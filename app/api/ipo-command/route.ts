import { kvStore } from "@/lib/kv-cache";
import { readVersionedSnapshot, snapshotResponse } from "@/lib/versioned-snapshot";

export const dynamic = "force-dynamic";
export async function GET() {
  const store = kvStore();
  const hit = store ? await readVersionedSnapshot(store, "ipo-command:v6") : null;
  return snapshotResponse(hit, { cards: [], filtered: [], filtered_count: 0, live: [], levels: [], blocks: [], post: [], brlm: [], dl: [], track: [], degraded: "snapshot unavailable" });
}
