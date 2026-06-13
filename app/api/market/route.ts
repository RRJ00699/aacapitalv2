import { NextRequest, NextResponse } from "next/server"
import { callAI } from "@/lib/ai"

export async function GET(req: NextRequest) {
  try {
    const prompt = `Search for current India VIX value today and Nifty 50 PCR from NSE. Also Nifty 50 and Bank Nifty levels.
Return ONLY raw JSON no markdown:
{"vix":{"value":14.5,"change":0.3,"changePct":2.1,"trend":"Rising"},"niftyPcr":{"value":0.85,"change":-0.05,"signal":"Neutral","callOI":45000000,"putOI":38250000},"nifty":{"value":24500,"change":120,"changePct":0.49},"bankNifty":{"value":52300,"change":210,"changePct":0.4},"fetchTime":"HH:MM IST"}`

    const text = await callAI({ messages: [{ role: "user", content: prompt }], maxTokens: 600, webSearch: true })
    const m = text.match(/\{[\s\S]*"vix"[\s\S]*\}/)
    if (m) return NextResponse.json({ ok: true, data: JSON.parse(m[0]), simulated: false })

    return NextResponse.json({ ok: true, simulated: true, data: {
      vix: { value: 14.2, change: 0.8, changePct: 5.9, trend: "Rising" },
      niftyPcr: { value: 0.82, change: -0.06, signal: "Buy Zone", callOI: 48200000, putOI: 39524000 },
      nifty: { value: 24412, change: 88, changePct: 0.36 },
      bankNifty: { value: 52180, change: 195, changePct: 0.37 },
      fetchTime: "Simulated",
    }})
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}
