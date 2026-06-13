// app/api/trade-journal/route.ts
// GET  - fetch saved trades + AI behavioral analysis
// POST - sync from Zerodha + run behavioral mirror

import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"
import { decrypt } from "@/lib/security/crypto"

function db() { return neon(process.env.DATABASE_URL!) }

async function callClaude(prompt: string): Promise<string> {
  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": process.env.ANTHROPIC_API_KEY ?? "",
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model: "claude-sonnet-4-20250514",
      max_tokens: 1000,
      messages: [{ role: "user", content: prompt }],
    }),
  })
  if (!res.ok) throw new Error(`Claude API ${res.status}`)
  const data = await res.json()
  return data.content?.[0]?.text ?? ""
}

export async function GET(_req: NextRequest) {
  try {
    const sql = db()
    const trades = await sql`
      SELECT * FROM trade_journal ORDER BY trade_date DESC LIMIT 100
    `
    const analysis = await sql`
      SELECT details FROM audit_log
      WHERE action = 'behavioral_mirror'
      ORDER BY created_at DESC LIMIT 1
    `.catch(() => [])

    return NextResponse.json({
      ok: true,
      trades,
      behavioral_analysis: analysis[0]?.details ?? null,
      total: trades.length,
    })
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "Unknown error"
    return NextResponse.json({ ok: false, error: msg }, { status: 500 })
  }
}

export async function POST(req: NextRequest) {
  try {
    const sql = db()
    const body = await req.json().catch(() => ({}))
    const runAI = body.run_ai !== false

    // 1. Get Zerodha session
    const sessions = await sql`
      SELECT access_token FROM kite_session ORDER BY created_at DESC LIMIT 1
    `
    if (!sessions.length) {
      return NextResponse.json({ ok: false, error: "No Zerodha session" }, { status: 401 })
    }
    const accessToken = decrypt(sessions[0].access_token as string)

    // 2. Fetch order history directly from Kite API
    let zerodhaOrders: Record<string, unknown>[] = []
    try {
      const kiteRes = await fetch("https://api.kite.trade/orders", {
        headers: {
          "X-Kite-Version": "3",
          "Authorization": `token ${process.env.KITE_API_KEY}:${accessToken}`,
        },
      })
      if (kiteRes.ok) {
        const kiteData = await kiteRes.json()
        zerodhaOrders = kiteData.data ?? []
      }
    } catch { /* work with existing DB data */ }

    // 3. Save new trades
    let newTradeCount = 0
    for (const order of zerodhaOrders) {
      if (order.status !== "COMPLETE") continue
      try {
        await sql`
          INSERT INTO trade_journal (
            broker_order_id, tradingsymbol, exchange, transaction_type,
            quantity, price, trade_date, product, order_type, status
          ) VALUES (
            ${order.order_id as string},
            ${order.tradingsymbol as string},
            ${order.exchange as string},
            ${order.transaction_type as string},
            ${order.filled_quantity as number},
            ${order.average_price as number},
            ${order.order_timestamp as string},
            ${order.product as string},
            ${order.order_type as string},
            'COMPLETE'
          )
          ON CONFLICT (broker_order_id) DO NOTHING
        `.catch(() => {})
        newTradeCount++
      } catch { /* skip individual */ }
    }

    // 4. Get all trades for analysis
    const allTrades = await sql`
      SELECT * FROM trade_journal ORDER BY trade_date DESC LIMIT 200
    `

    if (!allTrades.length) {
      return NextResponse.json({
        ok: true, new_trades: newTradeCount,
        message: "No trades found", behavioral_analysis: null,
      })
    }

    // 5. Run AI behavioral mirror
    let behavioralAnalysis = null
    if (runAI && allTrades.length >= 5) {
      const tradesSummary = allTrades.slice(0, 50).map(t => ({
        symbol: t.tradingsymbol, type: t.transaction_type,
        qty: t.quantity, price: t.price, date: t.trade_date, product: t.product,
      }))

      const prompt = `You are a trading behavioral analyst for an Indian retail investor using AACapital.

Analyse these trades and identify behavioral patterns, biases, and actionable insights.

Trades (most recent first):
${JSON.stringify(tradesSummary, null, 2)}

Return ONLY a JSON object (no markdown, no backticks):
{
  "win_rate": 0.0,
  "avg_hold_days": 0,
  "biggest_bias": "string",
  "pattern_summary": "2-3 sentence summary",
  "top_mistakes": ["mistake1", "mistake2", "mistake3"],
  "strengths": ["strength1", "strength2"],
  "recommendations": ["action1", "action2", "action3"],
  "risk_score": 0,
  "behavior_type": "IPO Trader|Swing Trader|Long-term|Mixed",
  "consistency_score": 0
}`

      try {
        const raw = await callClaude(prompt)
        const clean = raw.replace(/```json|```/g, "").trim()
        behavioralAnalysis = JSON.parse(clean)
        await sql`
          INSERT INTO audit_log (action, resource, details, created_at)
          VALUES ('behavioral_mirror', 'trade_journal', ${JSON.stringify(behavioralAnalysis)}, NOW())
        `.catch(() => {})
      } catch { /* skip if parse fails */ }
    }

    return NextResponse.json({
      ok: true,
      new_trades: newTradeCount,
      total_trades: allTrades.length,
      behavioral_analysis: behavioralAnalysis,
    })
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "Unknown error"
    return NextResponse.json({ ok: false, error: msg }, { status: 500 })
  }
}
