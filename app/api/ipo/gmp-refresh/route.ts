import { NextRequest, NextResponse } from "next/server"
import { IPO_PIPELINE } from "@/lib/ipo/pipeline"

async function fetchHtml(url: string): Promise<string> {
  try {
    const res = await fetch(url, {
      headers: { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" },
      signal: AbortSignal.timeout(8000),
    })
    return res.ok ? await res.text() : ""
  } catch { return "" }
}

async function extractGmp(html: string, name: string): Promise<number | null> {
  if (!html) return null
  try {
    const res = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: "claude-haiku-4-5-20251001",
        max_tokens: 50,
        system: "Return only a number or null. No explanation.",
        messages: [{ role: "user", content: `GMP in rupees for "${name}" from this page. Return number only or null.\n\n${html.slice(0, 2000)}` }]
      })
    })
    if (!res.ok) return null
    const d = await res.json()
    const n = parseFloat(d.content?.[0]?.text?.trim())
    return isNaN(n) ? null : n
  } catch { return null }
}

export async function GET(req: NextRequest) {
  const active = IPO_PIPELINE.filter(i => i.status === "OPEN" || i.status === "UPCOMING")
  const results = []

  for (const ipo of active) {
    const slug = ipo.name.toLowerCase().replace(/\s*\(.*?\)/g,"").replace(/[^a-z0-9]+/g,"-").replace(/(^-|-$)/g,"")
    const word = ipo.name.split(" ")[0].toLowerCase()
    let gmp: number | null = null
    let source = ""

    // InvestorGain → IPOWatch fallback
    for (const [url, src] of [
      [`https://www.investorgain.com/ipo/${slug}-ipo-gmp/`, "InvestorGain"],
      [`https://ipowatch.in/${slug}-ipo-gmp/`, "IPOWatch"],
    ] as [string,string][]) {
      if (gmp !== null) break
      const html = await fetchHtml(url)
      if (html && html.toLowerCase().includes(word)) {
        gmp = await extractGmp(html, ipo.name)
        if (gmp !== null) source = src
      }
    }

    results.push({ name: ipo.name, status: ipo.status, currentGmp: ipo.gmpPrice, freshGmp: gmp, source, changed: gmp !== null && gmp !== ipo.gmpPrice })
  }

  return NextResponse.json({
    ok: true,
    scrapedAt: new Date().toISOString(),
    total: active.length,
    updated: results.filter(r => r.changed).length,
    results,
  })
}
