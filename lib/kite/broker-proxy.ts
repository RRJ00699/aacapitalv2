import { readVersionedSnapshot, type SnapshotRead } from "@/lib/versioned-snapshot"
import type { SnapshotKV } from "@/lib/versioned-snapshot"

export type LiveOverlayState = "AVAILABLE" | "DEGRADED" | "BLOCKED"
export type BrokerQuote = {
  symbol: string
  instrument: string
  last_price: number
  open: number
  high: number
  low: number
  close: number
  volume: number
  total_buy_quantity: number
  total_sell_quantity: number
  depth: { buy: Array<{ price: number; quantity: number; orders?: number }>; sell: Array<{ price: number; quantity: number; orders?: number }> }
  as_of: string
}

export const IPO_LIVE_SNAPSHOT = "ipo-live-preopen:v2"
export const BROKER_TIMEOUT_MS = 4_500

const NSE_SYMBOL = /^[A-Z0-9][A-Z0-9&.-]{0,30}$/

export function istMinutes(d = new Date()): number {
  const parts = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hour12: false }).formatToParts(d)
  const h = Number(parts.find((p) => p.type === "hour")?.value ?? 0)
  const m = Number(parts.find((p) => p.type === "minute")?.value ?? 0)
  return h * 60 + m
}

export function inIpoDecisionWindow(d = new Date()): boolean {
  const mins = istMinutes(d)
  // Mirrors pipeline/config PREOPEN_START/END: 08:55–10:05 IST.
  // This bounded live-overlay window covers the 09:00–09:40 critical decision
  // period while allowing pre-open priming and immediate post-discovery fallback.
  return mins >= 8 * 60 + 55 && mins <= 10 * 60 + 5
}

export function normalizeSnapshotSymbol(value: unknown): string | null {
  if (typeof value !== "string") return null
  const symbol = value.trim().toUpperCase()
  return NSE_SYMBOL.test(symbol) ? symbol : null
}

export function approvedSymbolsFromSnapshot(payload: any): string[] {
  const rows = Array.isArray(payload?.listings) ? payload.listings : []
  const symbols = rows.map((row: any) => normalizeSnapshotSymbol(row?.sym ?? row?.symbol ?? row?.nse_symbol)).filter(Boolean) as string[]
  return [...new Set(symbols)].slice(0, 15)
}

export function snapshotAsOf(hit: SnapshotRead | null, payload: any): string | null {
  return String(payload?.snapshot_as_of ?? payload?.fetchedAt ?? hit?.version ?? "") || null
}

export async function readIpoLiveSnapshot(store: SnapshotKV | null): Promise<{ hit: SnapshotRead | null; payload: any | null; snapshot_as_of: string | null }> {
  const hit = store ? await readVersionedSnapshot(store, IPO_LIVE_SNAPSHOT) : null
  if (!hit) return { hit: null, payload: null, snapshot_as_of: null }
  const payload = JSON.parse(hit.payload)
  return { hit, payload, snapshot_as_of: snapshotAsOf(hit, payload) }
}

export async function fetchBrokerQuotes(params: {
  brokerUrl: string
  brokerSecret: string
  symbols: string[]
  fetchImpl?: typeof fetch
}): Promise<{ quotes: Record<string, BrokerQuote>; as_of: string }> {
  const fetcher = params.fetchImpl ?? fetch
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), BROKER_TIMEOUT_MS)
  try {
    const response = await fetcher(`${params.brokerUrl.replace(/\/$/, "")}/quotes`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "authorization": `Bearer ${params.brokerSecret}`,
      },
      body: JSON.stringify({ symbols: params.symbols, allowed_symbols: params.symbols }),
      signal: controller.signal,
    })
    if (!response.ok) throw new Error("broker_unavailable")
    const body = await response.json() as any
    if (!body?.ok || typeof body?.quotes !== "object") throw new Error("broker_unavailable")
    return { quotes: body.quotes, as_of: String(body.as_of || new Date().toISOString()) }
  } finally {
    clearTimeout(timeout)
  }
}

export function overlaySnapshot(payload: any, quotes: Record<string, BrokerQuote>, liveAsOf: string) {
  const listings = (Array.isArray(payload?.listings) ? payload.listings : []).map((row: any) => {
    const symbol = normalizeSnapshotSymbol(row?.sym ?? row?.symbol ?? row?.nse_symbol)
    const quote = symbol ? quotes[symbol] : undefined
    return quote ? { ...row, live_quote: quote, latest_observation: { ...(row.latest_observation ?? {}), ltp: quote.last_price, buy_qty: quote.total_buy_quantity, sell_qty: quote.total_sell_quantity, observed_at: quote.as_of, source: "broker-proxy" } } : row
  })
  return { ...payload, listings, book_live: true, live_overlay: "AVAILABLE" as const, live_as_of: liveAsOf, degradation_reason: null }
}
