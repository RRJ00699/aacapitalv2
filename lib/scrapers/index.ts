// ─────────────────────────────────────────────────────────────────────────────
// AACapital IPO Scraper Engine
// Fallback hierarchy per field per Section 9 of build prompt
// Confidence: HIGH | MEDIUM | LOW | MISSING
// ─────────────────────────────────────────────────────────────────────────────

export type Confidence = "HIGH" | "MEDIUM" | "LOW" | "MISSING"

export interface ScrapedField<T> {
  value: T | null
  source: string
  sourceUrl: string
  confidence: Confidence
}

export interface ScrapedIpoData {
  name: string
  // Subscription (fallback: Chittorgarh → InvestorGain → IPOWatch)
  qibX:      ScrapedField<number>
  niiX:      ScrapedField<number>
  retailX:   ScrapedField<number>
  employeeX: ScrapedField<number>
  totalX:    ScrapedField<number>
  // GMP (fallback: InvestorGain → IPOWatch → Chittorgarh → manual)
  gmpLatest: ScrapedField<number>
  gmpMin:    ScrapedField<number>
  gmpMax:    ScrapedField<number>
  gmpTrend:  number[]
  // Listing (fallback: NSE → BSE → IPOCentral → Chittorgarh)
  listingPrice:      ScrapedField<number>
  day1ClosePrice:    ScrapedField<number>
  listingGainPct:    ScrapedField<number>
  // Anchors (fallback: exchange filing → Chittorgarh → InvestorGain)
  anchors:           ScrapedField<string[]>
  // Financials (fallback: RHP → Screener → manual)
  revenueCAGR:       ScrapedField<number>
  patCAGR:           ScrapedField<number>
  roce:              ScrapedField<number>
  roe:               ScrapedField<number>
  debtEquity:        ScrapedField<number>
  peRatio:           ScrapedField<number>
  peerPE:            ScrapedField<number>
  // Meta
  dataQuality: string
  missingFields: string[]
  sourceAudit: Record<string, string>
}

function missing(field: string): ScrapedField<any> {
  return { value: null, source: "none", sourceUrl: "", confidence: "MISSING" }
}

function fromPipeline<T>(val: T | undefined, field: string): ScrapedField<T> {
  if (val == null) return missing(field)
  return { value: val, source: "pipeline", sourceUrl: "local", confidence: "HIGH" }
}

// Polite fetch with timeout + browser headers
async function politeGet(url: string, timeoutMs = 7000): Promise<string> {
  try {
    const res = await fetch(url, {
      headers: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
      },
      signal: AbortSignal.timeout(timeoutMs),
    })
    if (!res.ok) return ""
    return await res.text()
  } catch {
    return ""
  }
}

// Extract structured data using Claude API
async function extractWithClaude(html: string, ipoName: string, fields: string, schema: string): Promise<any> {
  try {
    const res = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: "claude-sonnet-4-20250514",
        max_tokens: 800,
        system: "You are a financial data extractor. Return ONLY valid JSON. No explanation, no markdown, no backticks.",
        messages: [{
          role: "user",
          content: `Extract ${fields} for IPO "${ipoName}" from this HTML.
Return JSON matching exactly: ${schema}
Use null for any field not found. Numbers only (no %, no x suffix).

HTML:
${html.slice(0, 4000)}`
        }]
      })
    })
    if (!res.ok) return {}
    const d = await res.json()
    const text = (d.content?.[0]?.text || "{}").replace(/```[a-z]*|```/g, "").trim()
    return JSON.parse(text)
  } catch {
    return {}
  }
}

// Slug helpers
const toSlug = (name: string) =>
  name.toLowerCase().replace(/\s*\(.*?\)\s*/g, "").replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "")

const firstWord = (name: string) => name.split(/[\s(]/)[0].toLowerCase()

// ─────────────────────────────────────────────────────────────────────────────
// GMP scraping — InvestorGain → IPOWatch → Chittorgarh
// ─────────────────────────────────────────────────────────────────────────────
async function scrapeGmp(name: string): Promise<{ latest: ScrapedField<number>; min: ScrapedField<number>; max: ScrapedField<number>; trend: number[] }> {
  const slug = toSlug(name)
  const word = firstWord(name)

  const sources = [
    { url: `https://www.investorgain.com/ipo/${slug}-ipo-gmp/`, name: "InvestorGain" },
    { url: `https://ipowatch.in/${slug}-ipo-gmp/`, name: "IPOWatch" },
    { url: `https://www.chittorgarh.com/ipo/${slug}-ipo/`, name: "Chittorgarh" },
  ]

  for (const src of sources) {
    const html = await politeGet(src.url)
    if (!html || !html.toLowerCase().includes(word)) continue

    const data = await extractWithClaude(html, name, "GMP data", `{
      "gmpLatest": number,
      "gmpMin": number,
      "gmpMax": number,
      "gmpTrend": [array of recent daily GMP numbers, oldest first]
    }`)

    if (data.gmpLatest != null || data.gmpMax != null) {
      const latest = data.gmpLatest ?? data.gmpMax
      return {
        latest: { value: latest, source: src.name, sourceUrl: src.url, confidence: "MEDIUM" },
        min:    { value: data.gmpMin ?? null, source: src.name, sourceUrl: src.url, confidence: "MEDIUM" },
        max:    { value: data.gmpMax ?? null, source: src.name, sourceUrl: src.url, confidence: "MEDIUM" },
        trend:  Array.isArray(data.gmpTrend) ? data.gmpTrend : [],
      }
    }
  }

  return {
    latest: missing("gmpLatest"),
    min:    missing("gmpMin"),
    max:    missing("gmpMax"),
    trend:  [],
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Subscription — Chittorgarh → InvestorGain → IPOWatch
// ─────────────────────────────────────────────────────────────────────────────
async function scrapeSubscription(name: string): Promise<{
  qib: ScrapedField<number>; nii: ScrapedField<number>
  retail: ScrapedField<number>; employee: ScrapedField<number>; total: ScrapedField<number>
}> {
  const slug = toSlug(name)
  const word = firstWord(name)

  const sources = [
    { url: `https://www.chittorgarh.com/ipo/${slug}-ipo/`, name: "Chittorgarh" },
    { url: `https://www.investorgain.com/ipo/${slug}-ipo/`, name: "InvestorGain" },
    { url: `https://ipowatch.in/${slug}-ipo/`, name: "IPOWatch" },
  ]

  for (const src of sources) {
    const html = await politeGet(src.url)
    if (!html || !html.toLowerCase().includes(word)) continue

    const data = await extractWithClaude(html, name, "subscription data", `{
      "qibX": number,
      "niiX": number,
      "retailX": number,
      "employeeX": number,
      "totalX": number
    }`)

    if (data.qibX != null || data.totalX != null) {
      const mk = (v: number | null) => ({
        value: v ?? null, source: src.name, sourceUrl: src.url,
        confidence: (v != null ? "MEDIUM" : "MISSING") as Confidence
      })
      return { qib: mk(data.qibX), nii: mk(data.niiX), retail: mk(data.retailX), employee: mk(data.employeeX), total: mk(data.totalX) }
    }
  }

  const none = (f: string) => missing(f)
  return { qib: none("qibX"), nii: none("niiX"), retail: none("retailX"), employee: none("employeeX"), total: none("totalX") }
}

// ─────────────────────────────────────────────────────────────────────────────
// Anchor investors — Chittorgarh → InvestorGain → IPOWatch
// ─────────────────────────────────────────────────────────────────────────────
async function scrapeAnchors(name: string): Promise<ScrapedField<string[]>> {
  const slug = toSlug(name)
  const word = firstWord(name)

  const sources = [
    { url: `https://www.chittorgarh.com/ipo/${slug}-ipo/anchor-investors/`, name: "Chittorgarh" },
    { url: `https://www.investorgain.com/ipo/${slug}-ipo/`, name: "InvestorGain" },
    { url: `https://ipowatch.in/${slug}-ipo/`, name: "IPOWatch" },
  ]

  for (const src of sources) {
    const html = await politeGet(src.url)
    if (!html || !html.toLowerCase().includes(word)) continue

    const data = await extractWithClaude(html, name, "anchor investor names", `{
      "anchors": ["investor name 1", "investor name 2", ...]
    }`)

    if (data.anchors?.length > 0) {
      return { value: data.anchors, source: src.name, sourceUrl: src.url, confidence: "MEDIUM" }
    }
  }
  return missing("anchors")
}

// ─────────────────────────────────────────────────────────────────────────────
// Main scraper — assembles all fields
// ─────────────────────────────────────────────────────────────────────────────
export async function scrapeIpoData(name: string, pipeline?: any): Promise<ScrapedIpoData> {
  // Run GMP + subscription + anchors in parallel
  const [gmpData, subData, anchorData] = await Promise.all([
    scrapeGmp(name),
    scrapeSubscription(name),
    scrapeAnchors(name),
  ])

  // Merge with pipeline data (pipeline = HIGH confidence baseline)
  const merge = <T>(scraped: ScrapedField<T>, pipelineVal: T | undefined): ScrapedField<T> => {
    if (scraped.confidence !== "MISSING") return scraped
    if (pipelineVal != null) return fromPipeline(pipelineVal, "")
    return scraped
  }

  const result: ScrapedIpoData = {
    name,
    qibX:       merge(subData.qib,     pipeline?.qibX),
    niiX:       merge(subData.nii,     pipeline?.niiX),
    retailX:    merge(subData.retail,  pipeline?.retailX),
    employeeX:  subData.employee,
    totalX:     merge(subData.total,   pipeline?.totalX),
    gmpLatest:  merge(gmpData.latest,  pipeline?.gmpPrice),
    gmpMin:     merge(gmpData.min,     pipeline?.gmpMin),
    gmpMax:     merge(gmpData.max,     pipeline?.gmpMax),
    gmpTrend:   gmpData.trend.length ? gmpData.trend : (pipeline?.gmpTrend || []),
    listingPrice:   { value: pipeline?.listingPrice ?? null, source: "pipeline", sourceUrl: "", confidence: pipeline?.listingPrice ? "HIGH" : "MISSING" },
    day1ClosePrice: missing("day1ClosePrice"),
    listingGainPct: missing("listingGainPct"),
    anchors:    merge(anchorData, pipeline?.anchors),
    revenueCAGR: fromPipeline(pipeline?.revenueCAGR, "revenueCAGR"),
    patCAGR:    fromPipeline(pipeline?.patCAGR, "patCAGR"),
    roce:       fromPipeline(pipeline?.roce, "roce"),
    roe:        fromPipeline(pipeline?.roe, "roe"),
    debtEquity: fromPipeline(pipeline?.debtEquity, "debtEquity"),
    peRatio:    fromPipeline(pipeline?.peRatio, "peRatio"),
    peerPE:     fromPipeline(pipeline?.peerPE, "peerPE"),
    dataQuality: "pending",
    missingFields: [],
    sourceAudit: {},
  }

  // Assess data quality
  const critical = ["qibX","niiX","retailX","gmpLatest","revenueCAGR","patCAGR","roce","anchors"]
  result.missingFields = critical.filter(f => (result as any)[f]?.confidence === "MISSING")
  const populated = critical.length - result.missingFields.length
  result.dataQuality = populated >= 7 ? "complete"
    : populated >= 5 ? "partial_no_financials"
    : populated >= 3 ? "partial_no_gmp"
    : result.missingFields.includes("qibX") ? "subscription_only"
    : "manual_review_required"

  // Source audit trail
  for (const [k, v] of Object.entries(result)) {
    if (v && typeof v === "object" && "sourceUrl" in v && v.sourceUrl)
      result.sourceAudit[k] = v.sourceUrl as string
  }

  return result
}

// ─────────────────────────────────────────────────────────────────────────────
// SBI Securities PDF parser — uses Claude to extract all engine fields
// ─────────────────────────────────────────────────────────────────────────────
export async function parseSbiSecReport(content: string): Promise<Record<string, any>> {
  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: "claude-sonnet-4-20250514",
      max_tokens: 2000,
      system: "You are a financial data extractor. Return ONLY valid JSON. No explanation, no markdown fences.",
      messages: [{
        role: "user",
        content: `Extract all IPO engine values from this broker research report.

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
  "peRatio": number,
  "peerPE": number,
  "peerLabel": "peer company name (PE)",
  "fcfPositive": true or false,
  "brokerReco": "Subscribe|Subscribe LT|Avoid|Neutral",
  "brokerNote": "one line summary of the recommendation reasoning",
  "promoterHoldingPostIpo": number,
  "anchors": ["anchor1", "anchor2"],
  "promoterClean": true or false,
  "noRegulatoryIssues": true or false,
  "capitalAllocationScore": 0-100,
  "executionTrackRecord": true or false,
  "industryReputation": 0-100,
  "gmpPrice": number or null
}

Report content:
${content.slice(0, 10000)}`
      }]
    })
  })

  if (!res.ok) return {}
  const d = await res.json()
  const text = (d.content?.[0]?.text || "{}").replace(/```[a-z]*|```/g, "").trim()
  try {
    return JSON.parse(text)
  } catch {
    return {}
  }
}
