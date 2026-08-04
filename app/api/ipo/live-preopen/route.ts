import { NextResponse } from "next/server";
import { kvStore } from "@/lib/kv-cache";
import { readVersionedSnapshot } from "@/lib/versioned-snapshot";

export const dynamic="force-dynamic";
/** Static, honest behavior until a no-daily-deployment credential design is approved. */
export async function GET() {
  const store=kvStore(); const hit=store?await readVersionedSnapshot(store,"ipo-live-preopen:v2"):null;
  if (!hit) return NextResponse.json({ok:true,window:"listing_date = IST-today",book_live:false,live_overlay:"BLOCKED",degraded:"snapshot unavailable; Kite overlay blocked",count:0,listings:[]},{headers:{"x-cache":"MISS"}});
  const payload=JSON.parse(hit.payload);
  return NextResponse.json({...payload,book_live:false,live_overlay:"BLOCKED",degraded:payload.degraded||"Kite overlay blocked pending safe credential automation"},{headers:{"x-cache":"HIT","x-snapshot-version":hit.version,...(hit.source==="previous"?{"x-snapshot-rollback":"previous"}:{})}});
}
