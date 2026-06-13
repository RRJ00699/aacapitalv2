// app/api/capital-deployment/route.ts
// GET  - current deployment recommendation (cached)
// POST - generate fresh AI deployment plan based on regime + portfolio + opportunities

import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

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
    const cached = await sql`
      SELECT details, created_at FROM audit_log
      WHERE action = 'capital_deployment_plan'
      ORDER BY created_at DESC
      LIMIT 1
    `.catch(() => [])

    if (!cached.length) {
      return NextResponse.json({ ok: true, plan: null, message: "No plan generated yet" })
    }
    return NextResponse.json({ ok: true, plan: cached[0].details, generated_at: cached[0].created_at })
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "Unknown error"
    return NextResponse.json({ ok: false, error: msg }, { status: 500 })
  }
}

export async function POST(req: NextRequest) {
  try {
    const sql = db()
    const body = await req.json()
    const { available_cash = 0, total_portfolio = 0, current_holdings = [], risk_appetite = "moderate" } = body

    // 1. Get market regime
    const snapshot = await sql`
      SELECT regime, nifty_close, pcr, fii_net FROM market_snapshot
      ORDER BY created_at DESC LIMIT 1
    `.catch(() => [])

    // 2. Get top DNA candidates
    const appUrl = process.env.NEXT_PUBLIC_APP_URL ?? "https://aacapital.vercel.app"
    const convRes = await fetch(`${appUrl}/api/multibagger-discovery?limit=10&min_score=55`)
      .then(r => r.json()).catch(() => ({ ok: false, data: [] }))

    // 3. Get active IPOs
    const ipoData = await sql`
      SELECT name, conviction_score, ev_score, listing_score FROM ipo_master
      WHERE status = 'open' OR status = 'upcoming'
      ORDER BY conviction_score DESC NULLS LAST LIMIT 5
    `.catch(() => [])

    // 4. Get user settings
    const settings = await sql`
      SELECT capital_goal, target_cagr, ipo_threshold FROM user_settings LIMIT 1
    `.catch(() => [])

    const regime = snapshot[0] ?? { regime: "NORMAL", nifty_close: 0 }
    const userSettings = settings[0] ?? { capital_goal: 0, target_cagr: 15, ipo_threshold: 75 }

    const prompt = `You are AACapital's Capital Deployment Optimizer for an Indian investor.

CURRENT CONTEXT:
- Available cash: ₹${available_cash.toLocaleString("en-IN")}
- Total portfolio value: ₹${total_portfolio.toLocaleString("en-IN")}
- Cash as % of portfolio: ${total_portfolio > 0 ? Math.round(available_cash / total_portfolio * 100) : 100}%
- Risk appetite: ${risk_appetite}
- Market regime: ${regime.regime ?? "NORMAL"}
- Nifty: ${regime.nifty_close ?? "N/A"} | PCR: ${regime.pcr ?? "N/A"} | FII: ${regime.fii_net ?? "N/A"}

CURRENT HOLDINGS (${current_holdings.length} positions):
${JSON.stringify(current_holdings.slice(0, 10), null, 2)}

TOP MULTIBAGGER CANDIDATES (DNA scored):
${JSON.stringify(convRes.data?.slice(0, 5) ?? [], null, 2)}

OPEN IPOs:
${JSON.stringify(ipoData, null, 2)}

USER GOALS:
- Capital goal: ₹${(userSettings.capital_goal || 0).toLocaleString("en-IN")}
- Target CAGR: ${userSettings.target_cagr ?? 15}%
- IPO conviction threshold: ${userSettings.ipo_threshold ?? 75}

Return ONLY a JSON object (no markdown, no backticks):
{
  "regime_assessment": "2 sentence market assessment",
  "deployment_mode": "AGGRESSIVE|MODERATE|DEFENSIVE|HOLD_CASH",
  "cash_to_deploy_pct": 0,
  "cash_to_hold_pct": 0,
  "allocations": [
    {
      "category": "IPO|Multibagger|Existing Position|Cash Reserve",
      "pct_of_available": 0,
      "amount": 0,
      "reasoning": "string",
      "specific_action": "string"
    }
  ],
  "top_action": "The single most important thing to do with capital right now",
  "risk_warning": "string or null",
  "expected_cagr_range": "X-Y%",
  "review_trigger": "What would make you change this plan"
}`

    const raw = await callClaude(prompt)
    let plan: any = null
    try {
      const clean = raw.replace(/```json|```/g, "").trim()
      plan = JSON.parse(clean)
      await sql`
        INSERT INTO audit_log (action, resource, details, created_at)
        VALUES ('capital_deployment_plan', 'portfolio', ${JSON.stringify(plan)}, NOW())
      `.catch(() => {})
    } catch { plan = { error: "Parse failed", raw } }

    return NextResponse.json({ ok: true, plan })
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "Unknown error"
    return NextResponse.json({ ok: false, error: msg }, { status: 500 })
  }
}
