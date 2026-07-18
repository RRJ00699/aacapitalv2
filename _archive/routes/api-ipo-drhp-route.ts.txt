import { NextRequest, NextResponse } from "next/server"

export const maxDuration = 60

export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData()
    const file = formData.get("file") as File | null
    if (!file) return NextResponse.json({ error: "No file uploaded" }, { status: 400 })

    const buffer = await file.arrayBuffer()
    const sizeMB = +(buffer.byteLength / (1024 * 1024)).toFixed(1)

    if (sizeMB > 28) {
      return NextResponse.json({
        error: `DRHP is ${sizeMB}MB — too large for single upload (limit ~28MB). Upload only the key chapters: Related Party Transactions, Risk Factors, Capital Structure, Statutory Auditor Report.`,
        tooLarge: true,
        sizeMB
      }, { status: 400 })
    }

    const base64 = Buffer.from(buffer).toString("base64")

    const res = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": process.env.ANTHROPIC_API_KEY!,
        "anthropic-version": "2023-06-01"
      },
      body: JSON.stringify({
        model: "claude-sonnet-4-20250514",
        max_tokens: 2000,
        system: "You are a SEBI-registered analyst specializing in DRHP red flag detection for institutional investors. Extract specific numbers and facts from the document. Return ONLY valid JSON. No markdown. Use null for fields not found in this document.",
        messages: [{
          role: "user",
          content: [
            {
              type: "document",
              source: { type: "base64", media_type: "application/pdf", data: base64 }
            },
            {
              type: "text",
              text: `Perform an institutional-grade DRHP red flag scan on this prospectus.

Extract exactly this JSON (use null if not found — never guess, only cite what is explicitly stated):
{
  "companyName": "exact company name from cover page",
  "issueSize": "total issue size in Cr",
  "rptAnalysis": {
    "totalRptPct": "RPT as % of revenue or total transactions (e.g. 12.3%) — look for Related Party Transactions section",
    "rptNature": "brief description of nature of RPTs (loans, purchases, services)",
    "keyRelatedParties": ["related entity 1", "related entity 2"],
    "rptFlag": "GREEN if <5%, AMBER if 5-15%, RED if >15% or undisclosed major transactions",
    "rptNote": "1 sentence — specific concern or clean signal"
  },
  "promoterPledge": {
    "pledgePct": "pledged shares as % of promoter holding",
    "pledgeAmount": "pledge amount in Cr if mentioned",
    "lender": "name of lender institution if mentioned",
    "pledgeFlag": "GREEN if 0%, AMBER if 1-10%, RED if >10%",
    "pledgeNote": "1 sentence"
  },
  "litigationRisk": {
    "materialCases": "number of material outstanding litigation cases",
    "totalContingentLiability": "total contingent liability in Cr",
    "taxDisputes": "tax dispute amount in Cr if disclosed",
    "litigationFlag": "GREEN if minimal/none, AMBER if moderate, RED if significant vs networth",
    "litigationNote": "1 sentence on the most significant case"
  },
  "auditorQuality": {
    "auditorName": "statutory auditor firm name",
    "auditorTier": "Big4 OR Mid-tier OR Small",
    "qualifications": ["any emphasis of matter or qualification from auditor report"],
    "auditorChanges": "any auditor resignation or change in last 3 years",
    "auditorFlag": "GREEN if Big4/reputed no qualifications, AMBER if mid-tier, RED if qualifications or resignation",
    "auditorNote": "1 sentence"
  },
  "customerConcentration": {
    "top1CustomerPct": "revenue % from single largest customer",
    "top5CustomerPct": "revenue % from top 5 customers",
    "keyCustomers": ["named customer 1 if disclosed"],
    "concentrationFlag": "GREEN if top5 <30%, AMBER if 30-50%, RED if >50%",
    "concentrationNote": "1 sentence"
  },
  "cashFlowQuality": {
    "cffoVsPatTrend": "comparison of CFO vs PAT — is CFO consistently lower? state the gap",
    "workingCapitalDays": "debtor days or working capital cycle if mentioned",
    "revenueRecognition": "any aggressive or unusual revenue recognition policy noted",
    "cashFlag": "GREEN if CFO > PAT consistently, AMBER if sometimes lower, RED if CFO regularly negative with positive PAT",
    "cashNote": "1 sentence"
  },
  "debtStructure": {
    "totalDebt": "total borrowings in Cr",
    "debtEquity": "D/E ratio",
    "covenants": "any restrictive covenants on IPO proceeds or operations",
    "debtFlag": "GREEN if D/E <0.5, AMBER if 0.5-1.5, RED if >1.5 or restrictive covenants"
  },
  "freshIssuePct": "fresh issue proceeds as % of total issue",
  "ofsPct": "OFS as % of total issue",
  "overallRiskScore": "0-100 integer — lower is cleaner. Weight: RPT 25%, Pledge 20%, Auditor 20%, Litigation 15%, Concentration 10%, Cash 10%",
  "overallFlag": "GREEN if <30 risk, AMBER if 30-60, RED if >60",
  "topRedFlags": ["top red flag 1 with specific number", "top red flag 2"],
  "greenFlags": ["specific positive 1", "specific positive 2"],
  "summary": "3 sentence institutional assessment of overall DRHP quality and recommendation to proceed or flag for deeper due diligence"
}`
            }
          ]
        }]
      })
    })

    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      console.error("Anthropic DRHP error:", res.status, err)
      return NextResponse.json({ error: `Claude API error: ${res.status}`, detail: err }, { status: 500 })
    }

    const d = await res.json()
    const text = (d.content?.[0]?.text || "{}").replace(/```json|```/g, "").trim()
    try {
      const flags = JSON.parse(text)
      return NextResponse.json({ ok: true, flags, filename: file.name, sizeMB })
    } catch {
      console.error("Failed to parse DRHP JSON:", text.slice(0, 200))
      return NextResponse.json({ error: "Failed to parse AI response" }, { status: 500 })
    }
  } catch (err: any) {
    console.error("DRHP route error:", err)
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}
