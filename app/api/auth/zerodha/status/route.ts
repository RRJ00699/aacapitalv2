import { NextResponse } from "next/server"
import { getBroker } from "@/lib/brokers"

export async function GET() {
  try {
    const broker = getBroker()
    const connected = await broker.isConnected()
    return NextResponse.json({
      connected,
      loginUrl: "/api/auth/zerodha",
      message: connected
        ? "Zerodha token available in Cloudflare broker storage."
        : "Zerodha token unavailable. Refresh the Cloudflare Kite token.",
    })
  } catch (err: any) {
    return NextResponse.json({ connected: false, message: err?.message ?? "status check failed" })
  }
}
