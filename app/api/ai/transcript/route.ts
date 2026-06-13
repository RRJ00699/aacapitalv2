import { NextRequest, NextResponse } from "next/server"
import { callAI } from "@/lib/ai"

export async function POST(req: NextRequest) {
  try {
    const { symbol, text, type } = await req.json()
    const content = text?.trim() || `Analyze the most recent earnings call transcript for ${symbol} listed company`

    const prompt = `You are an expert institutional equity analyst. Analyze this earnings transcript.
Document type: ${type || "earnings"}. Company: ${symbol || "Unknown"}.
${content.slice(0, 8000)}

Return ONLY valid JSON no markdown:
{"company":"Name","quarter":"Q3 FY25","docType":"Earnings Call","overallSignal":"BULLISH/NEUTRAL/BEARISH","managementTone":{"rating":"Improving/Stable/Deteriorating","score":8,"evidence":"quote","vsLastQuarter":"Higher/Same/Lower"},"confidence":{"level":"HIGH/MEDIUM/LOW","score":8,"vsLastQuarter":"Higher/Same/Lower","keyPhrases":["phrase"]},"guidance":{"revenue":"Raised/Maintained/Lowered","margin":"Expanding/Stable/Contracting","capex":"Raised/Maintained/Lowered","detail":"1 sentence"},"aiMention":{"frequency":"High/Medium/Low/None","context":"Offensive/Defensive/None","investmentSignal":"Positive/Neutral/Negative"},"keyMetrics":[{"metric":"Revenue Growth","value":"18% YoY","trend":"up"}],"redFlags":["flag"],"greenFlags":["flag"],"managementCredibility":{"score":8,"guidance_track_record":"Consistent/Mixed/Poor","comment":"1 sentence"},"orderBook":{"status":"Strong/Moderate/Weak","detail":""},"competitivePosition":"Gaining/Holding/Losing share","analystAction":"BUY/ACCUMULATE/HOLD/SELL","priceImplication":"Positive/Neutral/Negative","keyTakeaways":["point"],"watchFor":["monitor"]}`

    const text2 = await callAI({ messages: [{ role: "user", content: prompt }], maxTokens: 2000 })
    const result = JSON.parse(text2.replace(/```json|```/g, "").trim())
    return NextResponse.json({ ok: true, result })
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}
