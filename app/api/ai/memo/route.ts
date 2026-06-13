// app/api/ai/memo/route.ts
import { NextRequest, NextResponse } from "next/server"
import { callAI } from "@/lib/ai"
import { checkRateLimit } from "@/lib/security/ratelimit"
import { audit, clientIp } from "@/lib/security/audit"

export async function POST(req: NextRequest) {
  // Rate limit: 20 AI memo calls per hour per IP (P1-B #4)
  const ip = clientIp(req) ?? "unknown"
  const rl = await checkRateLimit(`ai-memo:${ip}`, 20)
  if (!rl.allowed) {
    return NextResponse.json(
      { error: "Rate limit exceeded. Try again in an hour." },
      { status: 429 }
    )
  }

  try {
    const { symbol, data } = await req.json()
    if (!symbol || !data)
      return NextResponse.json({ error: "Missing data" }, { status: 400 })

    const prompt = `You are an elite Indian institutional fund manager writing an Investment Committee Memo for ${symbol}.
DATA: Overall=${data.overall}/100 | Multibagger=${data.mbScore}/100 | BuyZone=${data.buyZone}/100 | Conviction=${data.convictionScore}/100
FUNDAMENTALS: RevCAGR=${data.rev3}% | PAT=${data.pat3}% | ROCE=${data.roce}% | ROE=${data.roe}% | DE=${data.debt}x | PE=${data.pe}x | PB=${data.pb}x | OpMarg=${data.opMarg}%
GOVERNANCE: Promoter=${data.promoter}% | Pledge=${data.pledge}% | Beneish=${data.beneish} | Piotroski=${data.piotroski}/9
TECHNICALS: RSI=${data.rsi} | EMAExt=${data.emaExtPct}% | Delivery=${data.del}%
EXCHANGE: ${data.exchange || "NSE"}
Return ONLY valid JSON no markdown:
{"headline":"punchy thesis","business":"2 sentence moat","industry":"1 sentence tailwind","buffett":"moat view","lynch":"multibagger potential","graham":"margin of safety","agrawal":"QGLP assessment","checklist":{"q1":"quality?","q2":"compound 5-10yr?","q3":"mgmt trustworthy?","q4":"capital allocation?","q5":"governance clean?","q6":"institutions accumulating?","q7":"valuation attractive?","q8":"smart money entering?","q9":"in buy zone?","q10":"5x/10x/20x potential?"},"missing_data":["gaps"],"bull_case":["p1","p2","p3"],"bear_case":["r1","r2"],"recommendation":"STRONG BUY/BUY/ACCUMULATE/HOLD/AVOID","target":"Rs XXX","stop":"Rs XXX","horizon":"X years","multibagger":"HIGH/MEDIUM/LOW â€" reason","position":"X% of portfolio","expected_cagr":"X-Y%","exit":"exit conditions","thesis":"2 sentence conviction"}`

    const text = await callAI({ messages: [{ role: "user", content: prompt }], maxTokens: 2000 })
    const memo = JSON.parse(text.replace(/```json|```/g, "").trim())

    await audit("ai.memo", { ip, detail: { symbol } })

    return NextResponse.json({ ok: true, memo })
  } catch (err: any) {
    console.error("AI memo error:", err)
    return NextResponse.json({ error: "Memo generation failed" }, { status: 500 })
  }
}
