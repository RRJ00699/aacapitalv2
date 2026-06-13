// app/api/broker/holdings/route.ts
import { NextResponse } from "next/server"
import { getBroker } from "@/lib/brokers"
import { audit, clientIp } from "@/lib/security/audit"

export async function GET(req: Request) {
  try {
    const broker    = getBroker()
    const connected = await broker.isConnected()
    if (!connected) {
      return NextResponse.json(
        { error: "Broker not connected", loginUrl: "/api/auth/zerodha" },
        { status: 401 }
      )
    }

    const holdings     = await broker.getHoldings()
    const funds        = await broker.getFunds()
    const totalPnl      = holdings.reduce((a, h) => a + h.pnl, 0)
    const totalInvested = holdings.reduce((a, h) => a + h.investedValue, 0)
    const totalCurrent  = holdings.reduce((a, h) => a + h.currentValue, 0)

    await audit("broker.holdings.read", { ip: clientIp(req) })

    return NextResponse.json({
      ok: true,
      holdings,
      summary: {
        totalHoldings: holdings.length,
        totalInvested,
        totalCurrent,
        totalPnl,
        totalPnlPct: totalInvested > 0 ? (totalPnl / totalInvested) * 100 : 0,
        availableFunds: funds.available,
      },
    })
  } catch (err: any) {
    console.error("Holdings error:", err)
    // Never expose raw errors (P1-B #6)
    return NextResponse.json({ error: "Failed to fetch holdings" }, { status: 500 })
  }
}
