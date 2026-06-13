import { NextResponse } from "next/server"

export async function GET() {
  const apiKey = process.env.KITE_API_KEY
  if (!apiKey) return NextResponse.json({ error: "KITE_API_KEY not set" }, { status: 500 })
  const loginUrl = `https://kite.zerodha.com/connect/login?api_key=${apiKey}&v=3`
  return NextResponse.redirect(loginUrl)
}
