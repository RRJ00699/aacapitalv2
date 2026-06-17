import { NextResponse } from "next/server"
import { getBroker } from "@/lib/brokers"

export const dynamic = "force-dynamic"

export async function GET() {
  try {
    const broker = getBroker()
    const connected = await broker.isConnected()
    return NextResponse.json({ ok: true, broker: broker.name, connected })
  } catch (err: any) {
    return NextResponse.json({ ok: false, connected: false, error: err?.message ?? "Broker status unavailable" })
  }
}
