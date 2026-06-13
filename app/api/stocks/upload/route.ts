import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

function getSQL() { return neon(process.env.DATABASE_URL!) }

async function ensureTable() {
  const sql = getSQL()
  await sql`
    CREATE TABLE IF NOT EXISTS stock_master (
      id                       SERIAL  PRIMARY KEY,
      symbol                   TEXT    NOT NULL UNIQUE,
      company_name             TEXT    NOT NULL,
      sector                   TEXT,
      market_cap               NUMERIC,
      revenue_cagr_3y          NUMERIC,
      profit_cagr_3y           NUMERIC,
      roe                      NUMERIC,
      roce                     NUMERIC,
      debt_equity              NUMERIC,
      promoter_holding         NUMERIC,
      promoter_pledge          NUMERIC,
      fii_holding              NUMERIC,
      dii_holding              NUMERIC,
      operating_margin         NUMERIC,
      pe_ratio                 NUMERIC,
      peg_ratio                NUMERIC,
      quality_score            INTEGER,
      risk_score               INTEGER,
      capital_protection_score INTEGER,
      tier                     TEXT,
      buy_zone_score           INTEGER,
      last_updated             TIMESTAMPTZ DEFAULT NOW(),
      source                   TEXT    DEFAULT 'csv_upload'
    )
  `
}

// ── Stock Quality Engine (formula-only, no paid data) ─────────────────────────

function calcQualityScore(r: any): number {
  let s = 0

  // ROCE (weight: 20)
  const roce = +r.roce || 0
  if (roce > 25) s += 20
  else if (roce > 20) s += 15
  else if (roce > 15) s += 8
  else if (roce < 10) s -= 5

  // ROE (weight: 15)
  const roe = +r.roe || 0
  if (roe > 22) s += 15
  else if (roe > 18) s += 10
  else if (roe > 12) s += 5

  // Profit CAGR 3Y (weight: 20)
  const pCagr = +r.profit_cagr_3y || 0
  if (pCagr > 25) s += 20
  else if (pCagr > 20) s += 15
  else if (pCagr > 12) s += 8
  else if (pCagr < 0) s -= 10

  // Revenue CAGR 3Y (weight: 15)
  const rCagr = +r.revenue_cagr_3y || 0
  if (rCagr > 20) s += 15
  else if (rCagr > 12) s += 10
  else if (rCagr < 5) s -= 5

  // D/E (weight: 15)
  const de = +r.debt_equity || 0
  if (de < 0.1) s += 15
  else if (de < 0.3) s += 12
  else if (de < 0.5) s += 8
  else if (de < 1.0) s += 3
  else if (de > 2.0) s -= 12

  // Promoter holding (weight: 10)
  const ph = +r.promoter_holding || 0
  if (ph > 65) s += 10
  else if (ph > 55) s += 7
  else if (ph > 45) s += 4
  else if (ph < 25) s -= 5

  // Operating margin (weight: 5)
  const opm = +r.operating_margin || 0
  if (opm > 25) s += 5
  else if (opm > 18) s += 3

  return Math.min(100, Math.max(0, s))
}

// ── Capital Protection Engine ─────────────────────────────────────────────────
// Based on: Piotroski F-score principles, Beneish M-score red flags, debt trends

function calcCapitalProtectionScore(r: any): number {
  let s = 75 // Start clean, deduct for red flags

  const de        = +r.debt_equity      || 0
  const pledge    = +r.promoter_pledge  || 0
  const ph        = +r.promoter_holding || 0
  const pCagr     = +r.profit_cagr_3y   || 0
  const roce      = +r.roce             || 0
  const opm       = +r.operating_margin || 0

  // Debt risk — biggest destroyer of capital
  if (de > 3.0)  s -= 30
  else if (de > 2.0)  s -= 20
  else if (de > 1.5)  s -= 10
  else if (de < 0.2)  s += 10

  // Promoter pledge — distress signal
  if (pledge > 50) s -= 25
  else if (pledge > 30) s -= 15
  else if (pledge > 15) s -= 8
  else if (pledge < 2)  s += 5

  // Promoter commitment
  if (ph < 25)  s -= 15
  else if (ph < 35) s -= 5
  else if (ph > 65) s += 5

  // Earnings quality
  if (pCagr < -10) s -= 20
  else if (pCagr < 0)  s -= 10

  // Capital efficiency
  if (roce < 8)  s -= 15
  else if (roce < 12) s -= 5

  // Margin health (Rajesh Exports red flag: unexplained margin expansion/collapse)
  if (opm < 3)  s -= 15
  else if (opm < 8)  s -= 5

  return Math.min(100, Math.max(0, s))
}

function calcTier(q: number, cp: number): string {
  if (q >= 80 && cp >= 75) return "Tier1A"
  if (q >= 70 && cp >= 65) return "Tier1B"
  if (q >= 58 && cp >= 55) return "Good"
  if (q >= 45)             return "Watch"
  return "Avoid"
}

// Buy zone score (simple — will upgrade when live prices available)
function calcBuyZoneScore(r: any): number {
  let s = 50
  const pe  = +r.pe_ratio || 0
  const peg = +r.peg_ratio || 0
  if (pe > 0 && pe < 15) s += 20
  else if (pe < 25) s += 10
  else if (pe > 50) s -= 15
  if (peg > 0 && peg < 1) s += 20
  else if (peg < 1.5) s += 10
  else if (peg > 3) s -= 10
  return Math.min(100, Math.max(0, s))
}

// ── CSV Parser (handles Screener.in export format) ────────────────────────────

function parseScreenerCSV(text: string): any[] {
  const lines = text.split("\n").filter(l => l.trim())
  if (lines.length < 2) return []

  // Normalise header names from Screener.in format
  const rawHeaders = lines[0].split(",").map(h => h.trim().replace(/"/g, ""))
  const headerMap: Record<string, string> = {
    "name":                   "company_name",
    "symbol":                 "symbol",
    "nse code":               "symbol",
    "bse code":               "symbol",
    "sector":                 "sector",
    "market cap":             "market_cap",
    "market cap (cr)":        "market_cap",
    "sales growth 3years":    "revenue_cagr_3y",
    "profit growth 3years":   "profit_cagr_3y",
    "roe":                    "roe",
    "roce":                   "roce",
    "debt to equity":         "debt_equity",
    "promoter holding":       "promoter_holding",
    "promoter pledge":        "promoter_pledge",
    "fii holding":            "fii_holding",
    "dii holding":            "dii_holding",
    "opm":                    "operating_margin",
    "operating profit margin":"operating_margin",
    "price to earning":       "pe_ratio",
    "p/e":                    "pe_ratio",
    "peg ratio":              "peg_ratio",
  }

  const headers = rawHeaders.map(h => headerMap[h.toLowerCase()] || h.toLowerCase().replace(/\s+/g,"_").replace(/[^a-z0-9_]/g,""))

  return lines.slice(1).map(line => {
    const vals = line.split(",").map(v => v.trim().replace(/"/g,""))
    const row: any = {}
    headers.forEach((h, i) => { row[h] = vals[i] || null })
    return row
  }).filter(r => r.symbol || r.company_name)
}

// ── Routes ────────────────────────────────────────────────────────────────────

export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData()
    const file = formData.get("file") as File
    if (!file) return NextResponse.json({ error: "No file uploaded" }, { status: 400 })

    const text    = await file.text()
    const rows    = parseScreenerCSV(text)
    if (rows.length === 0) return NextResponse.json({ error: "No valid rows parsed" }, { status: 400 })

    await ensureTable()
    const sql = getSQL()

    let inserted = 0
    const errors: string[] = []

    for (const r of rows) {
      const symbol = (r.symbol || r.company_name || "").toUpperCase().trim()
      if (!symbol) continue

      const q   = calcQualityScore(r)
      const cp  = calcCapitalProtectionScore(r)
      const bz  = calcBuyZoneScore(r)
      const tier = calcTier(q, cp)

      try {
        await sql`
          INSERT INTO stock_master (
            symbol, company_name, sector, market_cap,
            revenue_cagr_3y, profit_cagr_3y, roe, roce, debt_equity,
            promoter_holding, promoter_pledge, fii_holding, dii_holding,
            operating_margin, pe_ratio, peg_ratio,
            quality_score, risk_score, capital_protection_score,
            tier, buy_zone_score, last_updated, source
          ) VALUES (
            ${symbol},
            ${r.company_name || symbol},
            ${r.sector       || null},
            ${+r.market_cap  || null},
            ${+r.revenue_cagr_3y  || null}, ${+r.profit_cagr_3y || null},
            ${+r.roe  || null}, ${+r.roce || null}, ${+r.debt_equity || null},
            ${+r.promoter_holding || null}, ${+r.promoter_pledge || null},
            ${+r.fii_holding || null},      ${+r.dii_holding || null},
            ${+r.operating_margin || null},
            ${+r.pe_ratio || null}, ${+r.peg_ratio || null},
            ${q}, ${100 - q}, ${cp}, ${tier}, ${bz},
            NOW(), 'screener_csv'
          )
          ON CONFLICT (symbol) DO UPDATE SET
            quality_score            = EXCLUDED.quality_score,
            capital_protection_score = EXCLUDED.capital_protection_score,
            buy_zone_score           = EXCLUDED.buy_zone_score,
            tier                     = EXCLUDED.tier,
            last_updated             = NOW(),
            source                   = 'screener_csv'
        `
        inserted++
      } catch (e: any) {
        errors.push(`${symbol}: ${e.message}`)
      }
    }

    return NextResponse.json({
      ok: true, inserted,
      total: rows.length,
      errors: errors.slice(0, 5),
      message: `Imported ${inserted} stocks. Quality + Capital Protection scores calculated.`
    })
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}

export async function GET(req: NextRequest) {
  try {
    const tier   = req.nextUrl.searchParams.get("tier")
    const minQ   = +(req.nextUrl.searchParams.get("minQ") || "0")
    const minCP  = +(req.nextUrl.searchParams.get("minCP") || "0")

    await ensureTable()
    const sql = getSQL()

    const stocks = await sql`
      SELECT * FROM stock_master
      WHERE quality_score            >= ${minQ}
        AND capital_protection_score >= ${minCP}
        ${tier ? sql`AND tier = ${tier}` : sql``}
      ORDER BY quality_score DESC
      LIMIT 200
    `
    return NextResponse.json({ ok: true, stocks })
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}
