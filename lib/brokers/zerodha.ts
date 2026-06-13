// lib/brokers/zerodha.ts
import crypto from "crypto"
import { decrypt, isEncrypted } from "@/lib/security/crypto"
import type {
  BrokerProvider, BrokerProfile, BrokerFunds,
  BrokerHolding, BrokerPosition, BrokerOrder,
  BrokerQuote, BrokerCandle, PlaceOrderParams
} from "./interface"

const KITE_BASE = "https://api.kite.trade"

async function getToken(): Promise<string | null> {
  try {
    const { neon } = await import("@neondatabase/serverless")
    const sql = neon(process.env.DATABASE_URL!)
    const rows = await sql`
      SELECT access_token FROM kite_session
      WHERE expires_at > NOW()
      ORDER BY created_at DESC LIMIT 1
    `
    const stored: string | null = rows[0]?.access_token ?? null
    if (!stored) return null
    // Decrypt if encrypted (v1.xxx). Falls back to plaintext for any token
    // stored before encryption was enabled — re-encrypts on next Zerodha login.
    return isEncrypted(stored) ? decrypt(stored) : stored
  } catch { return null }
}

async function kite(path: string, method = "GET", body?: any): Promise<any> {
  const token = await getToken()
  if (!token) throw new Error("Zerodha not connected. Please login.")

  const headers: any = {
    "X-Kite-Version": "3",
    "Authorization": `token ${process.env.KITE_API_KEY}:${token}`,
  }

  const options: RequestInit = { method, headers }

  if (body && method !== "GET") {
    headers["Content-Type"] = "application/x-www-form-urlencoded"
    options.body = new URLSearchParams(body).toString()
  }

  const res = await fetch(`${KITE_BASE}${path}`, options)
  if (!res.ok) throw new Error(`Kite ${res.status}: ${await res.text()}`)
  const json = await res.json()
  if (json.status === "error") throw new Error(json.message)
  return json.data
}

export class ZerodhaProvider implements BrokerProvider {
  name = "zerodha"

  getLoginUrl(): string {
    return `https://kite.zerodha.com/connect/login?api_key=${process.env.KITE_API_KEY}&v=3`
  }

  async isConnected(): Promise<boolean> {
    const token = await getToken()
    return !!token
  }

  async getProfile(): Promise<BrokerProfile> {
    const d = await kite("/user/profile")
    return {
      userId: d.user_id,
      userName: d.user_name,
      email: d.email,
      broker: "Zerodha",
    }
  }

  async getFunds(): Promise<BrokerFunds> {
    const d = await kite("/user/margins")
    const equity = d?.equity ?? {}
    return {
      available: equity.available?.live_balance ?? 0,
      used: equity.utilised?.debits ?? 0,
      total: (equity.available?.live_balance ?? 0) + (equity.utilised?.debits ?? 0),
      currency: "INR",
    }
  }

  async getHoldings(): Promise<BrokerHolding[]> {
    const data = await kite("/portfolio/holdings")
    return (data ?? []).map((h: any) => ({
      symbol: h.tradingsymbol,
      exchange: h.exchange,
      quantity: h.quantity,
      avgPrice: h.average_price,
      lastPrice: h.last_price,
      pnl: h.pnl,
      pnlPct: h.average_price > 0
        ? ((h.last_price - h.average_price) / h.average_price) * 100
        : 0,
      currentValue: h.last_price * h.quantity,
      investedValue: h.average_price * h.quantity,
    }))
  }

  async getPositions(): Promise<BrokerPosition[]> {
    const data = await kite("/portfolio/positions")
    const all = [...(data?.net ?? []), ...(data?.day ?? [])]
    return all.map((p: any) => ({
      symbol: p.tradingsymbol,
      exchange: p.exchange,
      quantity: p.quantity,
      avgPrice: p.average_price,
      lastPrice: p.last_price,
      pnl: p.pnl,
      product: p.product,
      side: p.quantity > 0 ? "BUY" : "SELL",
    }))
  }

  async getOrders(): Promise<BrokerOrder[]> {
    const data = await kite("/orders")
    return (data ?? []).map((o: any) => ({
      orderId: o.order_id,
      symbol: o.tradingsymbol,
      exchange: o.exchange,
      quantity: o.quantity,
      price: o.price,
      status: o.status,
      side: o.transaction_type,
      product: o.product,
      timestamp: o.order_timestamp,
    }))
  }

  async getQuote(symbol: string, exchange: string): Promise<BrokerQuote> {
    const key = `${exchange}:${symbol}`
    const data = await kite(`/quote?i=${encodeURIComponent(key)}`)
    const q = data?.[key]
    if (!q) throw new Error(`No quote for ${symbol}`)
    const prev = q.ohlc?.close ?? q.last_price
    return {
      symbol, exchange,
      lastPrice: q.last_price,
      change: q.last_price - prev,
      changePct: ((q.last_price - prev) / (prev || 1)) * 100,
      open: q.ohlc?.open ?? 0,
      high: q.ohlc?.high ?? 0,
      low: q.ohlc?.low ?? 0,
      close: prev,
      volume: q.volume ?? 0,
      timestamp: new Date().toISOString(),
    }
  }

  async getQuotes(instruments: string[]): Promise<Record<string, BrokerQuote>> {
    const params = instruments.map(i => `i=${encodeURIComponent(i)}`).join("&")
    const data = await kite(`/quote?${params}`)
    const result: Record<string, BrokerQuote> = {}
    for (const [key, q] of Object.entries(data ?? {})) {
      const [exchange, symbol] = key.split(":")
      const qData = q as any
      const prev = qData.ohlc?.close ?? qData.last_price
      result[symbol] = {
        symbol, exchange,
        lastPrice: qData.last_price,
        change: qData.last_price - prev,
        changePct: ((qData.last_price - prev) / (prev || 1)) * 100,
        open: qData.ohlc?.open ?? 0,
        high: qData.ohlc?.high ?? 0,
        low: qData.ohlc?.low ?? 0,
        close: prev,
        volume: qData.volume ?? 0,
        timestamp: new Date().toISOString(),
      }
    }
    return result
  }

  async getHistoricalData(
    symbol: string, exchange: string,
    from: string, to: string, interval = "day"
  ): Promise<BrokerCandle[]> {
    const instruments = await kite(`/instruments/${exchange}`)
    const inst = instruments?.find((i: any) =>
      i.tradingsymbol === symbol && i.segment === exchange
    )
    if (!inst) throw new Error(`Instrument not found: ${symbol}`)
    const data = await kite(
      `/instruments/historical/${inst.instrument_token}/${interval}?from=${from}&to=${to}`
    )
    return (data?.candles ?? []).map((c: any[]) => ({
      timestamp: c[0], open: c[1], high: c[2], low: c[3], close: c[4], volume: c[5],
    }))
  }

  async placeOrder(params: PlaceOrderParams): Promise<string> {
    const data = await kite("/orders/regular", "POST", {
      tradingsymbol: params.symbol,
      exchange: params.exchange,
      transaction_type: params.side,
      order_type: params.orderType,
      quantity: params.quantity,
      product: params.product,
      price: params.price || 0,
      validity: params.validity || "DAY",
      tag: params.tag || "aacapital",
    })
    return data.order_id
  }

  async modifyOrder(orderId: string, params: Partial<PlaceOrderParams>): Promise<string> {
    const data = await kite(`/orders/regular/${orderId}`, "PUT", {
      quantity: params.quantity,
      price: params.price,
      order_type: params.orderType,
      validity: params.validity || "DAY",
    })
    return data.order_id
  }

  async cancelOrder(orderId: string): Promise<boolean> {
    await kite(`/orders/regular/${orderId}`, "DELETE")
    return true
  }
}

export async function exchangeKiteToken(requestToken: string): Promise<string> {
  const apiKey    = process.env.KITE_API_KEY!
  const apiSecret = process.env.KITE_API_SECRET!
  const checksum  = crypto
    .createHash("sha256")
    .update(apiKey + requestToken + apiSecret)
    .digest("hex")

  const res = await fetch("https://api.kite.trade/session/token", {
    method: "POST",
    headers: { "X-Kite-Version": "3", "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ api_key: apiKey, request_token: requestToken, checksum }),
  })

  if (!res.ok) throw new Error(`Token exchange failed: ${res.status}`)
  const data = await res.json()
  return data.data?.access_token
}
