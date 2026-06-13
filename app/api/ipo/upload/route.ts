import { NextRequest, NextResponse } from "next/server"
import { parseSbiSecReport } from "@/lib/scrapers/index"

export const maxDuration = 30

export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData()
    const file = formData.get("file") as File | null
    if (!file) return NextResponse.json({ error: "No file uploaded" }, { status: 400 })

    const isPdf = file.name.toLowerCase().endsWith(".pdf") || file.type === "application/pdf"
    let content = ""

    if (isPdf) {
      // For PDFs, convert to base64 and send to Claude as document
      const buffer = await file.arrayBuffer()
      const base64 = Buffer.from(buffer).toString("base64")

      const res = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: "claude-sonnet-4-20250514",
          max_tokens: 2000,
          system: "You are a financial data extractor. Return ONLY valid JSON. No explanation, no markdown fences.",
          messages: [{
            role: "user",
            content: [
              {
                type: "document",
                source: { type: "base64", media_type: "application/pdf", data: base64 }
              },
              {
                type: "text",
                text: `Extract all IPO engine values from this broker research report PDF.

Return exactly this JSON structure (use null for missing fields):
{
  "name": "IPO company name",
  "sector": "sector",
  "priceBandLow": number,
  "priceBandHigh": number,
  "issueSize": number,
  "lotSize": number,
  "freshIssuePct": number,
  "ofsPct": number,
  "openDate": "DD Mon YYYY",
  "closeDate": "DD Mon YYYY",
  "listingDate": "DD Mon YYYY",
  "revenueCAGR": number,
  "patCAGR": number,
  "roce": number,
  "roe": number,
  "debtEquity": number,
  "ebitdaMargin": number,
  "fcfPositive": true or false,
  "peRatio": number,
  "peerPE": number,
  "peerLabel": "peer name (PE)",
  "brokerReco": "Subscribe|Subscribe LT|Avoid|Neutral",
  "brokerNote": "one sentence summary of recommendation reasoning",
  "promoterHoldingPostIpo": number,
  "anchors": ["anchor name 1", "anchor name 2"],
  "promoterClean": true or false,
  "noRegulatoryIssues": true or false,
  "capitalAllocationScore": number 0-100,
  "executionTrackRecord": true or false,
  "industryReputation": number 0-100
}`
              }
            ]
          }]
        })
      })

      if (!res.ok) return NextResponse.json({ error: "Claude API error" }, { status: 500 })
      const d = await res.json()
      const text = (d.content?.[0]?.text || "{}").replace(/```[a-z]*|```/g, "").trim()
      try {
        const extracted = JSON.parse(text)
        const fieldCount = Object.keys(extracted).filter(k => extracted[k] != null).length
        return NextResponse.json({
          ok: true,
          extracted,
          filename: file.name,
          message: `Extracted ${fieldCount} fields from ${file.name}`,
          type: "pdf"
        })
      } catch {
        return NextResponse.json({ error: "Failed to parse Claude response" }, { status: 500 })
      }
    } else {
      // Plain text file
      content = await file.text()
      const { parseSbiSecReport } = await import("@/lib/scrapers/index")
      const extracted = await parseSbiSecReport(content)
      const fieldCount = Object.keys(extracted).filter(k => extracted[k] != null).length
      return NextResponse.json({
        ok: true,
        extracted,
        filename: file.name,
        message: `Extracted ${fieldCount} fields from ${file.name}`,
        type: "text"
      })
    }
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}
