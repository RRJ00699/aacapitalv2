// app/api/broker/quote/route.ts
import { NextRequest, NextResponse } from "next/server"
import { getBroker } from "@/lib/brokers"
import { audit, clientIp } from "@/lib/security/audit"

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url)
    const sym      = searchParams.get("sym")?.toUpperCase()
    const exchange = searchParams.get("exchange") || "NSE"

    if (!sym)
      return NextResponse.json({ error: "sym required" }, { status: 400 })

    const broker = getBroker()
    const connected = await broker.isConnected()
    if (!connected) {
      return NextResponse.json(
        { error: "Broker not connected", loginUrl: "/api/auth/zerodha" },
        { status: 401 }
      )
    }

    const quote = await broker.getQuote(sym, exchange)

    await audit("broker.quote.read", { ip: clientIp(req), detail: { sym, exchange } })

    return NextResponse.json({ ok: true, ...quote, source: "zerodha" })
  } catch (err: any) {
    console.error("Quote error:", err)
    return NextResponse.json({ error: "Failed to fetch quote" }, { status: 500 })
  }
}
