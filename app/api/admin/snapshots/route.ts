import { NextRequest, NextResponse } from "next/server";
import { kvStore } from "@/lib/kv-cache";
import { publishVersionedSnapshot } from "@/lib/versioned-snapshot";
import { PIPELINE_LIMITS } from "@/lib/config/pipeline";

export const dynamic = "force-dynamic";

type Publication = { name: string; payload: unknown };
const ALLOWED = /^(ipo-command:v6|ipo:index:v3|ipo-live-preopen:v2|journey:isin:[A-Z0-9]{12}:v1)$/;

/** Publication only: this Worker validates JSON supplied by the pipeline and writes KV.
 * It intentionally has no database/domain-builder import and cannot wake Neon. */
export async function POST(req: NextRequest) {
  if (!process.env.SNAPSHOT_PUBLISH_KEY || req.headers.get("x-aac-key") !== process.env.SNAPSHOT_PUBLISH_KEY)
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const store = kvStore();
  if (!store) return NextResponse.json({ error: "CACHE binding unavailable" }, { status: 503 });
  let body: { snapshots?: Publication[] };
  try { body = await req.json(); } catch { return NextResponse.json({ error: "invalid JSON" }, { status: 400 }); }
  if (!Array.isArray(body.snapshots) || !body.snapshots.length || body.snapshots.length > PIPELINE_LIMITS.SNAPSHOT_MAX_PUBLICATION_ITEMS)
    return NextResponse.json({ error: "snapshots must contain an allowed bounded item count" }, { status: 400 });
  const published: Record<string, string> = {};
  for (const item of body.snapshots) {
    if (!item || !ALLOWED.test(item.name) || item.payload === undefined)
      return NextResponse.json({ error: "invalid snapshot item" }, { status: 400 });
    JSON.stringify(item.payload);
  }
  for (const item of body.snapshots)
    published[item.name] = await publishVersionedSnapshot(store, item.name, item.payload);
  return NextResponse.json({ ok: true, published });
}

/** No read/list surface: publication credentials authorize POST only. */
export async function GET() {
  return NextResponse.json({ error: "unauthorized" }, { status: 401 });
}
