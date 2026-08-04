import { NextRequest, NextResponse } from "next/server";
import { kvStore } from "@/lib/kv-cache";
import { readVersionedSnapshot } from "@/lib/versioned-snapshot";
import { computeJourney } from "@/lib/v2/journey";

export async function GET(req: NextRequest) {
  const requestedIsin = req.nextUrl.searchParams.get("isin")?.toUpperCase();
  const sym = req.nextUrl.searchParams.get("sym")?.toUpperCase();
  if (!requestedIsin && !sym) return NextResponse.json({ ok:false,error:"isin or sym required" },{status:400});
  const store=kvStore();
  let isin=requestedIsin;
  if (!isin && store) {
    const index=await readVersionedSnapshot(store,"ipo:index:v3");
    if (index) isin=String((JSON.parse(index.payload).rows ?? []).find((r:Record<string,unknown>) => String(r.sym).toUpperCase()===sym)?.isin ?? "").toUpperCase();
  }
  const hit=store && isin ? await readVersionedSnapshot(store,`journey:isin:${isin}:v1`) : null;
  const resolvedSym=sym || (hit ? String(JSON.parse(hit.payload).sym||"").toUpperCase() : "");
  if (!hit) return NextResponse.json({...computeJourney([],resolvedSym),isin:isin||null,degraded:"snapshot unavailable"},{headers:{"x-cache":"MISS"}});
  const bundle=JSON.parse(hit.payload) as {rows?:Record<string,unknown>[]};
  return NextResponse.json({...computeJourney(bundle.rows??[],resolvedSym),isin},{headers:{"x-cache":"HIT","x-snapshot-version":hit.version,...(hit.source==="previous"?{"x-snapshot-rollback":"previous"}:{})}});
}
