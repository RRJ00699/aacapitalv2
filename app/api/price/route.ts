import { NextRequest, NextResponse } from "next/server"
import { detectExchange } from "@/lib/constants/stocks"
import { NseProvider } from "@/lib/providers/nse"
import { YahooProvider } from "@/lib/providers/yahoo"
import { SimulatedProvider } from "@/lib/providers/simulated"
import type { Exchange } from "@/lib/providers/interface"

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url)
    const sym = searchParams.get("sym")?.toUpperCase().trim()
    const exchangeParam = searchParams.get("exchange") as Exchange | null
    if (!sym) return NextResponse.json({ error: "Symbol required" }, { status: 400 })

    const exchange: Exchange = exchangeParam || detectExchange(sym)
    const isIndian = exchange === "NSE" || exchange === "BSE"

    try {
      if (isIndian) {
        const nse = new NseProvider()
        const price = await nse.getPrice(sym, exchange)
        return NextResponse.json({ ok: true, symbol: sym, exchange, source: "nse", ...price })
      } else {
        const yahoo = new YahooProvider()
        const price = await yahoo.getPrice(sym, exchange)
        return NextResponse.json({ ok: true, symbol: sym, exchange, source: "yahoo", ...price })
      }
    } catch (e: any) {
      // Fallback to simulated
      const sim = new SimulatedProvider()
      const price = await sim.getPrice(sym, exchange)
      return NextResponse.json({ ok: true, symbol: sym, exchange, source: "simulated", ...price })
    }
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}
