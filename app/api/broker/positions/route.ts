// app/api/broker/positions/route.ts
import { NextResponse } from "next/server"
import { getBroker } from "@/lib/brokers"
import { audit, clientIp } from "@/lib/security/audit"

export async function GET(req: Request) {
  try {
    const broker = getBroker()
    const connected = await broker.isConnected()
    if (!connected) {
      return NextResponse.json(
        { error: "Broker not connected", loginUrl: "/api/auth/zerodha" },
        { status: 401 }
      )
    }

    const positions = await broker.getPositions()

    await audit("broker.positions.read", { ip: clientIp(req) })

    return NextResponse.json({ ok: true, positions })
  } catch (err: any) {
    console.error("Positions error:", err)
    return NextResponse.json({ error: "Failed to fetch positions" }, { status: 500 })
  }
}
