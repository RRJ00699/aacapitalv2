export interface BrokerEnv {
  KITE_API_KEY: string
  KITE_ACCESS_TOKEN: string
  BROKER_PROXY_AUTH_SECRET: string
  KITE_BASE_URL?: string
}

type DepthLevel = { price: number; quantity: number; orders?: number }
type SanitizedQuote = {
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
  depth: { buy: DepthLevel[]; sell: DepthLevel[] }
  as_of: string
}

const MAX_SYMBOLS = 15
const CACHE_MS = 12_000
const KITE_TIMEOUT_MS = 4_000
const NSE_SYMBOL = /^[A-Z0-9][A-Z0-9&.-]{0,30}$/
const cache = new Map<string, { expires: number; body: string }>()

function json(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    ...init,
    headers: { "content-type": "application/json", ...(init.headers ?? {}) },
  })
}

function unauthorized() { return json({ ok: false, error: "unauthorized" }, { status: 401 }) }
function bad(error: string, status = 400) { return json({ ok: false, error }, { status }) }

function timingSafeEqual(a: string, b: string): boolean {
  const enc = new TextEncoder()
  const aa = enc.encode(a)
  const bb = enc.encode(b)
  let diff = aa.length ^ bb.length
  const max = Math.max(aa.length, bb.length)
  for (let i = 0; i < max; i++) diff |= (aa[i] ?? 0) ^ (bb[i] ?? 0)
  return diff === 0
}

function authenticated(req: Request, env: BrokerEnv): boolean {
  const expected = env.BROKER_PROXY_AUTH_SECRET || ""
  if (!expected) return false
  const auth = req.headers.get("authorization") || ""
  const bearer = auth.toLowerCase().startsWith("bearer ") ? auth.slice(7) : ""
  const header = req.headers.get("x-aac-broker-key") || ""
  return timingSafeEqual(bearer || header, expected)
}

function sanitizeSymbol(raw: unknown): string | null {
  if (typeof raw !== "string") return null
  const symbol = raw.trim().toUpperCase()
  if (!NSE_SYMBOL.test(symbol)) return null
  return symbol
}

function sanitizeDepth(levels: unknown): DepthLevel[] {
  if (!Array.isArray(levels)) return []
  return levels.slice(0, 5).map((level: any) => ({
    price: Number(level?.price ?? 0),
    quantity: Number(level?.quantity ?? 0),
    ...(level?.orders == null ? {} : { orders: Number(level.orders) }),
  }))
}

function sanitizeQuote(symbol: string, q: any, asOf: string): SanitizedQuote {
  const instrument = `NSE:${symbol}`
  return {
    symbol,
    instrument,
    last_price: Number(q?.last_price ?? 0),
    open: Number(q?.ohlc?.open ?? 0),
    high: Number(q?.ohlc?.high ?? 0),
    low: Number(q?.ohlc?.low ?? 0),
    close: Number(q?.ohlc?.close ?? 0),
    volume: Number(q?.volume ?? 0),
    total_buy_quantity: Number(q?.total_buy_quantity ?? q?.buy_quantity ?? 0),
    total_sell_quantity: Number(q?.total_sell_quantity ?? q?.sell_quantity ?? 0),
    depth: { buy: sanitizeDepth(q?.depth?.buy), sell: sanitizeDepth(q?.depth?.sell) },
    as_of: asOf,
  }
}

async function kiteQuotes(symbols: string[], env: BrokerEnv): Promise<Record<string, SanitizedQuote>> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), KITE_TIMEOUT_MS)
  try {
    const qs = symbols.map((s) => `i=${encodeURIComponent(`NSE:${s}`)}`).join("&")
    const base = (env.KITE_BASE_URL || "https://api.kite.trade").replace(/\/$/, "")
    const res = await fetch(`${base}/quote?${qs}`, {
      headers: {
        "X-Kite-Version": "3",
        "Authorization": `token ${env.KITE_API_KEY}:${env.KITE_ACCESS_TOKEN}`,
      },
      signal: controller.signal,
    })
    if (!res.ok) throw new Error("kite_quote_failed")
    const payload = await res.json() as any
    if (payload?.status === "error") throw new Error("kite_quote_failed")
    const data = payload?.data ?? {}
    const asOf = new Date().toISOString()
    const out: Record<string, SanitizedQuote> = {}
    for (const symbol of symbols) {
      const q = data[`NSE:${symbol}`]
      if (q) out[symbol] = sanitizeQuote(symbol, q, asOf)
    }
    return out
  } finally {
    clearTimeout(timeout)
  }
}

export async function handleBrokerRequest(req: Request, env: BrokerEnv): Promise<Response> {
  const url = new URL(req.url)
  if (url.pathname === "/health" && req.method === "GET") {
    if (!authenticated(req, env)) return unauthorized()
    return json({ ok: true, service: "kite-broker-proxy" })
  }
  if (url.pathname !== "/quotes") return bad("unsupported_endpoint", 404)
  if (req.method !== "POST") return bad("unsupported_method", 405)
  if (!authenticated(req, env)) return unauthorized()

  let payload: any
  try { payload = await req.json() } catch { return bad("invalid_json") }
  const requested = Array.isArray(payload?.symbols) ? payload.symbols : []
  const allowedRaw = Array.isArray(payload?.allowed_symbols) ? payload.allowed_symbols : []
  const symbols = requested.map(sanitizeSymbol)
  const allowed = new Set(allowedRaw.map(sanitizeSymbol).filter(Boolean) as string[])
  if (!symbols.length || symbols.some((s: string | null) => !s)) return bad("invalid_symbols")
  const unique = [...new Set(symbols as string[])]
  if (unique.length > MAX_SYMBOLS) return bad("too_many_symbols", 413)
  if (!allowed.size) return bad("empty_allow_list")
  if (unique.some((s) => !allowed.has(s))) return bad("symbol_not_allowed", 403)

  const cacheKey = unique.slice().sort().join(",")
  const hit = cache.get(cacheKey)
  if (hit && hit.expires > Date.now()) return new Response(hit.body, { headers: { "content-type": "application/json", "x-cache": "HIT" } })

  try {
    const quotes = await kiteQuotes(unique, env)
    const body = JSON.stringify({ ok: true, quotes, as_of: new Date().toISOString() })
    cache.set(cacheKey, { expires: Date.now() + CACHE_MS, body })
    return new Response(body, { headers: { "content-type": "application/json", "x-cache": "MISS" } })
  } catch {
    return json({ ok: false, error: "broker_unavailable" }, { status: 502 })
  }
}

export default { fetch: handleBrokerRequest }
