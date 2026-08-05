import { NextResponse } from "next/server";
import { getCloudflareContext } from "@opennextjs/cloudflare";
import { kvStore } from "@/lib/kv-cache";
import { fetchBrokerQuotes, inIpoDecisionWindow, approvedSymbolsFromSnapshot, readIpoLiveSnapshot, overlaySnapshot } from "@/lib/kite/broker-proxy";

export const dynamic="force-dynamic";
// Snapshot key remains "ipo-live-preopen:v2"; static fallback remains live_overlay:"BLOCKED" when broker is unavailable or out of window.

type BrokerEnv = { KITE_BROKER_PROXY_URL?: string; KITE_BROKER_PROXY_AUTH_SECRET?: string };

function publicEnv(): BrokerEnv {
  try { return getCloudflareContext().env as unknown as BrokerEnv } catch { return process.env as BrokerEnv }
}

function fallback(payload: any, snapshot_as_of: string | null, state: "DEGRADED" | "BLOCKED", reason: string, status = 200, headers: Record<string,string> = {}) {
  return NextResponse.json({ ...(payload ?? { ok:true, window:"listing_date = IST-today", count:0, listings:[] }), book_live:false, live_overlay:state, live_as_of:null, snapshot_as_of, degradation_reason:reason }, { status, headers })
}

export async function GET() {
  const store=kvStore();
  const { hit, payload, snapshot_as_of } = await readIpoLiveSnapshot(store);
  const headers={"x-cache":hit?"HIT":"MISS",...(hit?.version?{"x-snapshot-version":hit.version}:{}),...(hit?.source==="previous"?{"x-snapshot-rollback":"previous"}:{})};
  if (!payload) return fallback(null, null, "BLOCKED", "snapshot_unavailable", 200, headers);
  if (!inIpoDecisionWindow()) return fallback(payload, snapshot_as_of, "BLOCKED", "outside_ist_decision_window", 200, headers);

  const symbols = approvedSymbolsFromSnapshot(payload);
  if (!symbols.length) return fallback(payload, snapshot_as_of, "BLOCKED", "no_listing_day_symbols", 200, headers);

  const env = publicEnv();
  if (!env.KITE_BROKER_PROXY_URL || !env.KITE_BROKER_PROXY_AUTH_SECRET) return fallback(payload, snapshot_as_of, "BLOCKED", "broker_not_configured", 200, headers);

  try {
    const { quotes, as_of } = await fetchBrokerQuotes({ brokerUrl: env.KITE_BROKER_PROXY_URL, brokerSecret: env.KITE_BROKER_PROXY_AUTH_SECRET, symbols });
    return NextResponse.json({ ...overlaySnapshot(payload, quotes, as_of), snapshot_as_of }, { headers });
  } catch {
    return fallback(payload, snapshot_as_of, "DEGRADED", "broker_unavailable", 200, headers);
  }
}
