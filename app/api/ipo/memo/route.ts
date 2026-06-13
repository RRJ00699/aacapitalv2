import { NextRequest, NextResponse } from "next/server"

export const maxDuration = 30

export async function POST(req: NextRequest) {
  try {
    const { ipo } = await req.json()
    if (!ipo) return NextResponse.json({ error: "Missing IPO data" }, { status: 400 })

    const s = ipo.score || {}

    const prompt = `You are a senior Indian institutional fund manager writing a pre-IPO Investment Committee Memo.

IPO: ${ipo.name} | Sector: ${ipo.sector} | Issue Size: ₹${ipo.issueSize}Cr
Price Band: ₹${ipo.priceBandLow}–₹${ipo.priceBandHigh} | GMP: ₹${ipo.gmpPrice || 0} (${ipo.gmpPrice && ipo.priceBandHigh ? ((ipo.gmpPrice / ipo.priceBandHigh) * 100).toFixed(1) : 0}%)
Status: ${ipo.status} | Lot Size: ${ipo.lotSize || "TBD"}

SUBSCRIPTION DATA:
QIB: ${ipo.qibX || ipo.qib || 0}x | NII: ${ipo.niiX || ipo.hni || 0}x | Retail: ${ipo.retailX || ipo.retail || 0}x

SCORES:
Listing Score: ${s.listingScore || 0}/100 | Business Quality: ${s.businessScore || 0}/100
Management: ${s.managementScore || 0}/100 | Risk: ${s.risk?.score || 0}/100
Multibagger Probability: ${s.multibaggerProb || 0}% | Anchor Score: ${s.anchorScore || 0}/100
Anchor Signal: ${s.anchorValidation?.label || "N/A"}
Engine Recommendation: ${s.recommendation || "Watch"}

FINANCIALS:
Rev CAGR: ${ipo.revenueCAGR || 0}% | PAT CAGR: ${ipo.patCAGR || 0}%
ROCE: ${ipo.roce || 0}% | ROE: ${ipo.roe || 0}%
D/E: ${ipo.debtEquity || 0}x | EBITDA Margin: ${ipo.ebitdaMargin || 0}%
PE: ${ipo.peRatio || 0}x | Peer PE: ${ipo.peerPE || 0}x (${ipo.peerLabel || "peers"})
FCF Positive: ${ipo.fcfPositive ?? "unknown"}
Fresh Issue: ${ipo.freshIssuePct || 0}% | OFS: ${ipo.ofsPct || 100}%
Promoter Post-IPO: ${ipo.promoterHoldingPostIpo || 0}%

ANCHORS: ${(ipo.anchors || []).join(", ") || "Not yet disclosed"}
BROKER: ${ipo.brokerReco || "N/A"} — ${ipo.brokerNote || ""}

MARKET REGIME: 2026 COLD (avg +2%, 42% positive). Cold market = reduce GMP weight 30%, higher bar for aggressive apply.

You are writing for an institutional IC. Be direct, specific, and data-driven. No generics.

Return ONLY valid JSON, no markdown backticks:
{
  "executiveSummary": "2-3 sentence punchy IC summary with specific numbers",
  "recommendation": "APPLY AGGRESSIVELY|APPLY — LONG-TERM HOLD|LISTING TRADE ONLY|APPLY RETAIL ONLY|WATCH|AVOID",
  "confidence": "HIGH|MEDIUM|LOW",
  "confidenceReason": "one sentence why this confidence level",
  "targetListingGain": "X–Y% range",
  "targetT12M": "X–Y% range",
  "bullCase": ["specific point with data", "specific point", "specific point"],
  "bearCase": ["specific risk with number", "specific risk"],
  "valuationAnalysis": "PE vs peers, fresh issue quality, fair value vs issue price — 2 sentences with numbers",
  "anchorAnalysis": "specific anchors named, tier assessment, trap vs confirmation signal — 2 sentences",
  "dnaMatch": "Most similar historical IPO, why, and what it returned on D1 and 6M",
  "listingDayStrategy": "Entry at GMP ₹X. Sell target ₹X–₹X by 12PM. Stop loss if opens below ₹X.",
  "keyRisk": "single biggest risk in one precise sentence",
  "positionSizing": "X lots retail | avoid if [condition]",
  "exitCondition": "specific exit trigger",
  "missing": ["specific data gap 1", "specific data gap 2"]
}`

    const res = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": process.env.ANTHROPIC_API_KEY!,
        "anthropic-version": "2023-06-01"
      },
      body: JSON.stringify({
        model: "claude-sonnet-4-20250514",
        max_tokens: 1500,
        messages: [{ role: "user", content: prompt }]
      })
    })

    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      console.error("Anthropic IPO memo error:", res.status, err)
      return NextResponse.json({ error: `Claude API error: ${res.status}`, detail: err }, { status: 500 })
    }

    const d = await res.json()
    const text = (d.content?.[0]?.text || "{}").replace(/```json|```/g, "").trim()
    try {
      const memo = JSON.parse(text)
      return NextResponse.json({ ok: true, memo })
    } catch {
      console.error("Failed to parse memo JSON:", text.slice(0, 200))
      return NextResponse.json({ error: "Failed to parse AI response" }, { status: 500 })
    }
  } catch (err: any) {
    console.error("IPO memo route error:", err)
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}
