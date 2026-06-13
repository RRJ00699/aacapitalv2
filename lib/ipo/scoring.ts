// ─────────────────────────────────────────────────────────────────────────────
// AACapital IPO Engine v2.0
// Two separate models — never mixed:
//   Model 1: Listing Gain Engine (D1 performance)
//   Model 2: Business Quality Engine (6M–3Y performance)
// ─────────────────────────────────────────────────────────────────────────────

import { scoreAnchors } from "./anchors"

// ── Data shape ────────────────────────────────────────────────────────────────
export interface IpoData {
  name: string
  sector: string
  issueSize: number
  freshIssuePct: number
  ofsPct: number
  priceBandLow: number
  priceBandHigh: number
  lotSize?: number

  // Anchor
  anchors: string[]

  // Subscription
  retailX?: number
  niiX?: number
  qibX?: number
  totalX?: number

  // Financials
  revenueCAGR?: number
  patCAGR?: number
  roe?: number
  roce?: number
  debtEquity?: number
  ebitdaMargin?: number
  fcfPositive?: boolean
  peRatio?: number
  pbRatio?: number
  evEbitda?: number
  peerPE?: number
  peerLabel?: string

  // GMP
  gmpPrice?: number
  gmpTrend?: number[]

  // Management quality inputs
  promoterHoldingPostIpo?: number   // % e.g. 68
  promoterClean?: boolean           // no pledge, no litigation
  auditorOk?: boolean               // big-4 or reputable regional
  noRegulatoryIssues?: boolean
  relatedPartyTxPct?: number        // RPT as % of revenue — lower is better
  capitalAllocationScore?: number   // 0–100: has company reinvested well historically?
  executionTrackRecord?: boolean    // delivered on past guidance?
  industryReputation?: number       // 0–100: known brand / respected management
  drhpFiled?: boolean

  // Market context
  niftyTrend?: "bull" | "neutral" | "bear"
  vix?: number
  pcr?: number
  giftNiftyPct?: number

  // Status
  status?: "UPCOMING" | "OPEN" | "CLOSED" | "LISTED"
  listingDate?: string
  listingPrice?: number

  // Broker
  brokerReco?: string
  brokerNote?: string
}

// ─────────────────────────────────────────────────────────────────────────────
// SECTOR MOMENTUM TABLE
// Updated based on real listing data 2020–2026
// ─────────────────────────────────────────────────────────────────────────────
const SECTOR_MOMENTUM: Record<string, number> = {
  // Defense (Paras +171%, IdeaForge +93%, Cyient DLM +59%, DCX +49%)
  "Defense":               92,
  "Defense Electronics":   92,
  "Defense Drones":        90,
  "Defense/Aerospace":     88,
  "Defense/Shipbuilding":  82,

  // Solar / Renewable (Premier +96%, Waaree +70%, NTPC Green +4%)
  "Solar Manufacturing":   88,
  "Renewable Energy":      82,
  "Renewable/PSU":         72,
  "Solar/EPC":             80,
  "Clean Energy":          78,
  "Renewable/Bioenergy":   70,

  // EMS / Electronics (Kaynes +18% listing → +145% at 12M, Netweb +82%, DCX +49%)
  "EMS/Electronics":       90,
  "Electronics":           82,
  "IT Infrastructure":     85,
  "IT Services":           78,
  "IT Services/Auto":      80,

  // Financial Infrastructure (NSDL +10%, CDSL +76%, HDFC AMC +65%)
  "Financial Infrastructure": 88,
  "Asset Management":      82,
  "Fintech":               72,
  "Fintech/Payments":      68,
  "Fintech/Wealth":        75,

  // NBFC / Housing Finance (Bajaj HF +114%, HDB Fin +13%)
  "Housing Finance":       82,
  "NBFC":                  72,
  "NBFC/Tata Group":       80,
  "NBFC/HDFC":             78,

  // Specialty Chemicals (Tatva +113%, Rossari +75%, Aether +21%)
  "Specialty Chemicals":   80,
  "Pharma/CDMO":           78,
  "Pharma":                72,
  "Pharma API":            70,
  "Pharma Excipients":     76,

  // Consumer brands / D2C
  "D2C/Beauty":            65,
  "Beauty Ecommerce":      68,
  "D2C/Furniture":         60,
  "Retail/Apparel":        62,
  "Jewellery Retail":      65,
  "FMCG":                  65,
  "FMCG/Food":             62,
  "QSR":                   68,

  // Infrastructure EPC
  "Infrastructure EPC":    75,
  "Ports/Infrastructure":  78,
  "Power EPC":             80,
  "Cables/Wires":          72,

  // Tech / SaaS
  "Data Analytics":        82,
  "SaaS":                  78,
  "Travel Tech":           70,
  "EdTech":                52,

  // Metals / Commodities
  "Steel/Wires":           68,
  "Steel/Pipes":           65,
  "Metals Recycling/Aluminium": 62,
  "Coal/PSU":              55,
  "Mining/PSU Consultancy": 58,

  // Weak / declining
  "Logistics":             58,
  "Real Estate":           55,
  "Microfinance":          50,
  "Gaming":                48,
}

function getSectorMomentum(sector: string): number {
  if (SECTOR_MOMENTUM[sector]) return SECTOR_MOMENTUM[sector]
  // Fuzzy match
  const key = Object.keys(SECTOR_MOMENTUM).find(k =>
    sector.toLowerCase().includes(k.toLowerCase().split("/")[0]) ||
    k.toLowerCase().includes(sector.toLowerCase().split("/")[0])
  )
  return key ? SECTOR_MOMENTUM[key] : 60
}

// ─────────────────────────────────────────────────────────────────────────────
// MARKET REGIME ENGINE
// Based on real calibration: 2020-2026 data
// ─────────────────────────────────────────────────────────────────────────────
export interface MarketRegime {
  label: "HOT" | "NORMAL" | "COLD"
  score: number        // 0–100 for scoring
  gmpEfficiency: number // % of GMP realised at listing
}

function calcMarketRegime(d: IpoData): MarketRegime {
  const vix = d.vix ?? 15
  const trend = d.niftyTrend ?? "neutral"
  const pcr = d.pcr ?? 0.9

  // Calibrated:
  // 2024 HOT: vix ~12, avg +34%, 89% positive
  // 2025 NORMAL: vix ~14, avg +9%, 68% positive
  // 2026 COLD: vix >18, avg +2%, 42% positive
  let score = 50

  if (vix < 12)      score += 30
  else if (vix < 15) score += 15
  else if (vix < 18) score -= 5
  else               score -= 25

  if (trend === "bull") score += 15
  else if (trend === "bear") score -= 20

  if (pcr < 0.7)      score += 15
  else if (pcr < 0.9) score += 5
  else if (pcr > 1.2) score -= 15

  if (d.giftNiftyPct !== undefined) {
    if (d.giftNiftyPct > 0.5) score += 8
    else if (d.giftNiftyPct < -0.5) score -= 12
  }

  score = Math.max(0, Math.min(100, score))

  if (score >= 65) return { label:"HOT",    score, gmpEfficiency: 0.70 }
  if (score >= 40) return { label:"NORMAL",  score, gmpEfficiency: 0.60 }
  return              { label:"COLD",   score, gmpEfficiency: 0.50 }
}

// ─────────────────────────────────────────────────────────────────────────────
// ANCHOR VALIDATION SCORE
// Key insight: anchor quality × subscription strength
// High anchor + low sub = institutional trap
// High anchor + high sub = institutional confirmation
// ─────────────────────────────────────────────────────────────────────────────
function calcAnchorValidation(d: IpoData): { score: number; label: string; detail: string } {
  const anchorResult = scoreAnchors(d.anchors || [])
  const anchorQuality = anchorResult.score  // 0–100

  const qib = d.qibX ?? 0
  const nii = d.niiX ?? 0

  // Subscription strength signal (institutional demand)
  const subStrength = qib > 0 || nii > 0
    ? Math.min(100, (Math.min(qib, 200) / 200 * 50) + (Math.min(nii, 200) / 200 * 50))
    : 30 // unknown — assume moderate

  // Combined: both must be high to confirm
  const combined = (anchorQuality * 0.5) + (subStrength * 0.5)

  // Institutional trap: anchor ≥85 but sub very weak
  const isTrap = anchorQuality >= 85 && qib < 10 && nii < 5
  if (isTrap) return {
    score: Math.round(combined * 0.5),
    label: "⚠ Institutional Trap",
    detail: `Anchor quality ${anchorQuality} but QIB ${qib}x NII ${nii}x — institutions anchored but not subscribing`
  }

  // Institutional confirmation: both strong
  const isConfirm = anchorQuality >= 75 && qib >= 50 && nii >= 30
  if (isConfirm) return {
    score: Math.round(combined),
    label: "✅ Institutional Confirmation",
    detail: `Anchor quality ${anchorQuality} + QIB ${qib}x + NII ${nii}x = maximum conviction`
  }

  return {
    score: Math.round(combined),
    label: combined >= 65 ? "Strong" : combined >= 45 ? "Moderate" : "Weak",
    detail: `Anchor ${anchorQuality}/100 × Sub strength ${Math.round(subStrength)}/100`
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// MODEL 1 — LISTING GAIN ENGINE
// NII 25% | Retail 20% | QIB 20% | GMP 15% | Market Regime 10% | Anchor Validation 10%
// Calibrated from 2024 real data correlations
// ─────────────────────────────────────────────────────────────────────────────
function calcListingScore(d: IpoData, regime: MarketRegime): {
  total: number
  components: Record<string, number>
  applyRating: string
  gmpScenario: GmpScenario
} {
  const issuePrice = d.priceBandHigh || d.priceBandLow || 100

  // NII/HNI — strongest predictor (0.758 correlation, 2024 data)
  // Hot market: becomes even stronger; NII 900x in 2021 → Paras +171%
  const nii = d.niiX ?? 0
  const niiScore = nii >= 200 ? 100 : nii >= 100 ? 90 : nii >= 50 ? 75 :
                   nii >= 20  ? 58  : nii >= 5   ? 38 : nii > 0 ? 20 : 35
  const niiWeighted = niiScore * 0.25

  // Retail — surprisingly strong (0.746, 2024)
  const retail = d.retailX ?? 0
  const retailScore = retail >= 50 ? 100 : retail >= 25 ? 88 : retail >= 15 ? 72 :
                      retail >= 8  ? 55  : retail >= 3  ? 35 : retail > 0 ? 18 : 30
  const retailWeighted = retailScore * 0.20

  // QIB — strong but less differentiated (0.733)
  const qib = d.qibX ?? 0
  const qibScore = qib >= 150 ? 100 : qib >= 80 ? 88 : qib >= 40 ? 72 :
                   qib >= 15  ? 55  : qib >= 5  ? 35 : qib > 0 ? 18 : 30
  const qibWeighted = qibScore * 0.20

  // GMP — weakest predictor (0.511), regime-adjusted
  const gmpPct = d.gmpPrice ? (d.gmpPrice / issuePrice) * 100 : 0
  const gmpScore = gmpPct >= 40 ? 100 : gmpPct >= 25 ? 85 : gmpPct >= 15 ? 68 :
                   gmpPct >= 8  ? 50  : gmpPct >= 3  ? 32 : gmpPct > 0 ? 15 : 20
  // Cold market: GMP less reliable
  const gmpAdjusted = regime.label === "COLD"   ? gmpScore * 0.70 :
                      regime.label === "NORMAL"  ? gmpScore * 0.85 : gmpScore
  const gmpWeighted = gmpAdjusted * 0.15

  // Market Regime
  const regimeWeighted = regime.score * 0.10

  // Anchor Validation (not raw anchor quality)
  const av = calcAnchorValidation(d)
  const avWeighted = av.score * 0.10

  const total = Math.round(niiWeighted + retailWeighted + qibWeighted + gmpWeighted + regimeWeighted + avWeighted)

  // Risk deductions for listing
  let penalty = 0
  if (d.ofsPct > 90)           penalty += 8
  if (d.ofsPct > 70)           penalty += 5
  if (!d.fcfPositive)          penalty += 3
  if ((d.debtEquity ?? 0) > 2) penalty += 4
  const final = Math.max(0, Math.min(100, total - penalty))

  const applyRating = final >= 80 ? "Apply Aggressively"
    : final >= 65 ? "Apply — Retail"
    : final >= 50 ? "Listing-Day Trade"
    : final >= 35 ? "Watch"
    : "Avoid"

  // GMP Scenario
  const gmpScenario = calcGmpScenario(d, regime)

  return {
    total: final,
    components: {
      nii: Math.round(niiWeighted),
      retail: Math.round(retailWeighted),
      qib: Math.round(qibWeighted),
      gmp: Math.round(gmpWeighted),
      regime: Math.round(regimeWeighted),
      anchorValidation: Math.round(avWeighted),
    },
    applyRating,
    gmpScenario,
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// MODEL 2 — BUSINESS QUALITY ENGINE
// Rev CAGR 20% | PAT CAGR 20% | ROCE 15% | ROE 15% | Sector 10% | Anchor 10% | Fresh 10%
// ─────────────────────────────────────────────────────────────────────────────
function calcBusinessScore(d: IpoData): {
  total: number
  components: Record<string, number>
  multibaggerProb: number
  longTermRating: string
} {
  const rev = d.revenueCAGR ?? 0
  const revScore = rev >= 40 ? 100 : rev >= 25 ? 85 : rev >= 15 ? 68 :
                   rev >= 8  ? 50  : rev >= 0  ? 30 : 10
  const revWeighted = revScore * 0.20

  const pat = d.patCAGR ?? 0
  const patScore = pat >= 60 ? 100 : pat >= 35 ? 88 : pat >= 20 ? 72 :
                   pat >= 10 ? 55  : pat >= 0  ? 32 : 5
  const patWeighted = patScore * 0.20

  const roce = d.roce ?? 0
  const roceScore = roce >= 40 ? 100 : roce >= 25 ? 85 : roce >= 18 ? 68 :
                    roce >= 12 ? 48  : roce >= 0  ? 25 : 10
  const roceWeighted = roceScore * 0.15

  const roe = d.roe ?? 0
  const roeScore = roe >= 30 ? 100 : roe >= 20 ? 82 : roe >= 15 ? 65 :
                   roe >= 10 ? 45  : roe >= 0  ? 22 : 10
  const roeWeighted = roeScore * 0.15

  const sectorMomentum = getSectorMomentum(d.sector)
  const sectorWeighted = sectorMomentum * 0.10

  const anchorRaw = scoreAnchors(d.anchors || []).score
  const anchorWeighted = anchorRaw * 0.10

  // Fresh issue bonus/penalty
  const freshScore = d.freshIssuePct >= 70 ? 100
    : d.freshIssuePct >= 50 ? 75
    : d.freshIssuePct >= 30 ? 45
    : d.freshIssuePct >= 10 ? 25 : 5
  const freshWeighted = freshScore * 0.10

  const base = Math.round(revWeighted + patWeighted + roceWeighted + roeWeighted +
                           sectorWeighted + anchorWeighted + freshWeighted)

  // Bonus/penalty
  let adj = 0
  if (d.fcfPositive)            adj += 5
  if ((d.debtEquity ?? 0) < 0.3) adj += 5
  if ((d.debtEquity ?? 0) > 1.5) adj -= 10
  if (d.ebitdaMargin && d.ebitdaMargin >= 20) adj += 5
  const total = Math.max(0, Math.min(100, base + adj))

  // Multibagger probability — based on benchmarks:
  // Kaynes: rev 45% CAGR, roce 22%, EMS sector → went +145% in 12M
  // Netweb: rev 60%+ CAGR, roce 35%+, IT infra → +120% at 12M
  // DOMS: rev 20%+, roce 28%, consumer → +55% at 12M
  const multibaggerFactors = [
    rev >= 30 ? 1 : 0,
    pat >= 30 ? 1 : 0,
    roce >= 20 ? 1 : 0,
    sectorMomentum >= 80 ? 1 : 0,
    d.freshIssuePct >= 50 ? 1 : 0,
    anchorRaw >= 80 ? 1 : 0,
    (d.debtEquity ?? 1) < 0.5 ? 1 : 0,
  ]
  const multibaggerProb = Math.round((multibaggerFactors.reduce((a, b) => a + b, 0) / 7) * 100)

  const longTermRating = total >= 80 ? "Long-Term Compounder"
    : total >= 65 ? "Quality Business — Hold 12M"
    : total >= 50 ? "Moderate — Exit on listing pop"
    : total >= 35 ? "Weak — Listing trade only"
    : "Avoid"

  return {
    total,
    components: {
      revCagr: Math.round(revWeighted),
      patCagr: Math.round(patWeighted),
      roce: Math.round(roceWeighted),
      roe: Math.round(roeWeighted),
      sector: Math.round(sectorWeighted),
      anchor: Math.round(anchorWeighted),
      freshIssue: Math.round(freshWeighted),
    },
    multibaggerProb,
    longTermRating,
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// MANAGEMENT QUALITY ENGINE
// The hidden factor that identifies future winners early
// Kaynes, Netweb, DOMS had excellent management scores pre-listing
// ─────────────────────────────────────────────────────────────────────────────
function calcManagementScore(d: IpoData): {
  total: number
  components: Record<string, number>
  flags: string[]
  positives: string[]
} {
  const flags: string[] = []
  const positives: string[] = []
  let score = 40 // base — unknown

  // 1. Promoter holding post IPO (15 pts)
  // High holding = skin in the game = alignment
  // Low holding after OFS = cashing out signal
  const ph = d.promoterHoldingPostIpo ?? 0
  const phScore = ph >= 70 ? 15 : ph >= 55 ? 12 : ph >= 40 ? 8 : ph >= 25 ? 4 : 0
  score += phScore
  if (ph >= 65) positives.push(`Promoter holding ${ph}% post-IPO — high skin in game`)
  if (ph < 35 && ph > 0) flags.push(`Low promoter holding ${ph}% — potential exit concern`)

  // 2. Clean promoter — no pledge, litigation (15 pts)
  if (d.promoterClean === true)  { score += 15; positives.push("Clean promoter — no pledge, no litigation") }
  if (d.promoterClean === false) { score -= 10; flags.push("Promoter issues flagged — check pledge / litigation") }

  // 3. Auditor quality (10 pts)
  if (d.auditorOk === true)  { score += 10; positives.push("Reputable auditor") }
  if (d.auditorOk === false) { score -= 8;  flags.push("Weak auditor — due diligence required") }

  // 4. Related party transactions (10 pts)
  // Lower RPT % = cleaner governance
  const rpt = d.relatedPartyTxPct ?? 5 // assume moderate if unknown
  const rptScore = rpt <= 2 ? 10 : rpt <= 5 ? 7 : rpt <= 10 ? 4 : 0
  score += rptScore
  if (rpt > 10) flags.push(`High related party transactions ${rpt}% of revenue — governance risk`)
  if (rpt <= 2) positives.push("Very low related party transactions")

  // 5. No regulatory issues (10 pts)
  if (d.noRegulatoryIssues === true)  { score += 10; positives.push("No regulatory issues") }
  if (d.noRegulatoryIssues === false) { score -= 8;  flags.push("Regulatory issues in DRHP — read carefully") }

  // 6. Capital allocation history (0–100 → 10 pts)
  const ca = d.capitalAllocationScore ?? 50
  score += Math.round(ca / 10)
  if (ca >= 75) positives.push("Strong capital allocation history — management invests wisely")
  if (ca <= 30) flags.push("Weak capital allocation — management has wasted capital historically")

  // 7. Execution track record (10 pts)
  if (d.executionTrackRecord === true)  { score += 10; positives.push("Delivered on past guidance / targets") }
  if (d.executionTrackRecord === false) { score -= 5;  flags.push("Missed past guidance — execution concern") }

  // 8. Industry reputation (10 pts from 0–100 input)
  const rep = d.industryReputation ?? 50
  score += Math.round(rep / 10)
  if (rep >= 75) positives.push("Strong industry reputation — respected management team")

  const total = Math.max(0, Math.min(100, score))
  return {
    total,
    components: {
      promoterHolding: phScore,
      promoterClean: d.promoterClean ? 15 : 0,
      auditor: d.auditorOk ? 10 : 0,
      rpt: rptScore,
      regulatory: d.noRegulatoryIssues ? 10 : 0,
      capitalAllocation: Math.round(ca / 10),
      execution: d.executionTrackRecord ? 10 : 0,
      reputation: Math.round(rep / 10),
    },
    flags,
    positives,
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// RISK ENGINE
// ─────────────────────────────────────────────────────────────────────────────
function calcRisk(d: IpoData): { level: "LOW" | "MEDIUM" | "HIGH" | "EXTREME"; score: number; flags: string[] } {
  const flags: string[] = []
  let risk = 0

  if (d.ofsPct > 70)                  { risk += 20; flags.push(`High OFS ${d.ofsPct}% — promoters exiting`) }
  if (d.ofsPct > 90)                  { risk += 10; flags.push("Near 100% OFS — zero fresh capital raised") }
  if ((d.debtEquity ?? 0) > 1)        { risk += 15; flags.push(`D/E ratio ${d.debtEquity}x — elevated debt`) }
  if ((d.roce ?? 20) < 12)            { risk += 15; flags.push(`ROCE ${d.roce ?? "?"}% below threshold`) }
  if ((d.patCAGR ?? 0) < 0)           { risk += 20; flags.push("Negative PAT CAGR — profitability declining") }
  if (!d.fcfPositive)                  { risk += 8;  flags.push("Negative FCF — cash burn") }
  if (d.auditorOk === false)           { risk += 12; flags.push("Auditor concern") }
  if (d.promoterClean === false)       { risk += 15; flags.push("Promoter issues") }
  if (d.noRegulatoryIssues === false)  { risk += 10; flags.push("Regulatory risk") }

  const av = calcAnchorValidation(d)
  if (av.label.includes("Trap"))       { risk += 15; flags.push(av.label) }

  if ((d.relatedPartyTxPct ?? 0) > 10) { risk += 10; flags.push("High RPT") }
  if ((d.promoterHoldingPostIpo ?? 50) < 30) { risk += 10; flags.push("Low promoter holding post-IPO") }

  risk = Math.min(100, risk)
  const level = risk >= 65 ? "EXTREME" : risk >= 45 ? "HIGH" : risk >= 25 ? "MEDIUM" : "LOW"
  return { level, score: risk, flags }
}

// ─────────────────────────────────────────────────────────────────────────────
// GMP SCENARIO ENGINE
// ─────────────────────────────────────────────────────────────────────────────
export interface GmpScenario {
  issuePrice: number
  gmpPrice: number
  gmpEntryPrice: number
  // Scenario 1: Buy at GMP
  bullCase: number
  baseCase: number
  bearCase: number
  buyAtGmpUpside: number
  buyAtGmpDownside: number
  verdict: string
  verdictColor: string
  // Scenario 2: Bad listing day (GMP -20%)
  badDayListingPrice: number
  badDayFromIssue: number
  badDayFromGmp: number
  badDayRating: string
  // Scenario 3: GMP evaporates
  gmpEvaporatesFromGmp: number
  // GMP capture scenarios
  listing25pct: number
  listing50pct: number
  listing75pct: number
}

function calcGmpScenario(d: IpoData, regime: MarketRegime): GmpScenario {
  const issuePrice = d.priceBandHigh || d.priceBandLow || 100
  const gmp = d.gmpPrice || 0
  const entry = issuePrice + gmp
  const eff = regime.gmpEfficiency

  const bull = Math.round(issuePrice + gmp * 0.90)
  const base = Math.round(issuePrice + gmp * eff)
  const bear = Math.round(issuePrice - gmp * 0.20)

  const upside   = gmp > 0 ? +((bull - entry) / entry * 100).toFixed(1) : 0
  const downside = gmp > 0 ? +((bear - entry) / entry * 100).toFixed(1) : 0

  const badDayPrice = Math.round(issuePrice + gmp * 0.80 * -0.20 + issuePrice * 0.02)
  const badDayFromIssue = +((badDayPrice - issuePrice) / issuePrice * 100).toFixed(1)
  const badDayFromGmp   = +((badDayPrice - entry) / entry * 100).toFixed(1)

  let verdict = "", verdictColor = "#6b7280"
  if (gmp <= 0) {
    verdict = "No GMP signal"
  } else if (upside >= 15) {
    verdict = `Attractive — ${upside}% upside if listing holds`
    verdictColor = "#15803d"
  } else if (upside >= 5) {
    verdict = "Moderate risk/reward at GMP entry"
    verdictColor = "#d97706"
  } else {
    verdict = "Thin upside at GMP — consider IPO application only"
    verdictColor = "#dc2626"
  }

  return {
    issuePrice, gmpPrice: gmp, gmpEntryPrice: Math.round(entry),
    bullCase: bull, baseCase: base, bearCase: bear,
    buyAtGmpUpside: upside, buyAtGmpDownside: downside,
    verdict, verdictColor,
    badDayListingPrice: badDayPrice,
    badDayFromIssue, badDayFromGmp,
    badDayRating: badDayFromGmp < -10
      ? "High risk at GMP entry on bad day — position size carefully"
      : "Manageable risk on bad day at GMP price",
    gmpEvaporatesFromGmp: +((issuePrice - entry) / entry * 100).toFixed(1),
    listing25pct: Math.round(issuePrice + gmp * 0.25),
    listing50pct: Math.round(issuePrice + gmp * 0.50),
    listing75pct: Math.round(issuePrice + gmp * 0.75),
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// OFS / FRESH ISSUE ENGINE
// ─────────────────────────────────────────────────────────────────────────────
function calcIssueStructureScore(d: IpoData): { score: number; label: string; adj: number } {
  const fresh = d.freshIssuePct
  let score = 50, adj = 0, label = ""

  if (fresh >= 70)      { score = 85; adj = +15; label = "Fresh >70% — growth capital ✅" }
  else if (fresh >= 50) { score = 65; adj = +5;  label = "Mixed — partial fresh issue" }
  else if (fresh >= 30) { score = 45; adj = 0;   label = "OFS-heavy — read carefully" }
  else if (fresh > 0)   { score = 30; adj = -10; label = "High OFS — mostly exit" }
  else                  { score = 15; adj = -25; label = "100% OFS — promoters fully exiting" }

  return { score, label, adj }
}

// ─────────────────────────────────────────────────────────────────────────────
// VALUATION ENGINE
// ─────────────────────────────────────────────────────────────────────────────
function calcValuationScore(d: IpoData): number {
  if (!d.peRatio || !d.peerPE) return 50
  const discount = (d.peerPE - d.peRatio) / d.peerPE
  if (discount >= 0.30) return 90
  if (discount >= 0.15) return 75
  if (discount >= 0)    return 58
  if (discount >= -0.15)return 42
  if (discount >= -0.30)return 28
  return 15
}

// ─────────────────────────────────────────────────────────────────────────────
// MAIN SCORE FUNCTION
// ─────────────────────────────────────────────────────────────────────────────
export interface IpoScore {
  // Model 1 — Listing
  listingScore: number
  listingRating: string
  listingComponents: Record<string, number>

  // Model 2 — Business Quality
  businessScore: number
  businessRating: string
  businessComponents: Record<string, number>
  multibaggerProb: number

  // Sub-engines
  managementScore: number
  managementComponents: Record<string, number>
  managementFlags: string[]
  managementPositives: string[]

  anchorValidation: { score: number; label: string; detail: string }
  issueStructure: { score: number; label: string; adj: number }
  valuationScore: number
  sectorMomentum: number
  regime: MarketRegime
  risk: { level: string; score: number; flags: string[] }

  // GMP scenarios
  gmpScenario: GmpScenario

  // Overall recommendation
  recommendation: string
  confidence: "Low" | "Medium" | "High" | "Very High"

  // UI compat (used by existing components)
  total: number
  anchorScore: number
  anchorComponents: Record<string, number>
  businessScore_: number
  subscriptionScore: number
  issueStructureScore: number
  marketRegimeScore: number
  gmpScore: number
  historicalScore: number
  riskMultiplier: number
  applyRating: string
  flags: string[]
  greens: string[]
  bearCase: number
  baseCase: number
  bullCase: number
  listingBuyScore: number
  listingBuyRating: string
  contraryScore: number
  postListingRating: string
}

export function calcScore(d: IpoData): IpoScore {
  const regime       = calcMarketRegime(d)
  const listing      = calcListingScore(d, regime)
  const business     = calcBusinessScore(d)
  const management   = calcManagementScore(d)
  const av           = calcAnchorValidation(d)
  const issueSt      = calcIssueStructureScore(d)
  const valuation    = calcValuationScore(d)
  const sectorMom    = getSectorMomentum(d.sector)
  const risk         = calcRisk(d)
  const gmpScenario  = calcGmpScenario(d, regime)
  const anchorResult = scoreAnchors(d.anchors || [])

  // Final recommendation uses both models
  const listingGood   = listing.total >= 65
  const businessGood  = business.total >= 65
  const riskLow       = risk.level === "LOW" || risk.level === "MEDIUM"
  const multibagger   = business.multibaggerProb >= 60

  let recommendation = ""
  let confidence: "Low" | "Medium" | "High" | "Very High" = "Medium"

  if (listing.total >= 80 && businessGood && riskLow) {
    recommendation = "Apply Aggressively"
    confidence = "Very High"
  } else if (listing.total >= 65 && multibagger && riskLow) {
    recommendation = "Apply — Long-Term Hold"
    confidence = "High"
  } else if (listing.total >= 65 && !businessGood) {
    recommendation = "Apply — Listing Trade Only"
    confidence = "High"
  } else if (!listingGood && businessGood && riskLow) {
    recommendation = "Long-Term Compounder — Buy on Listing Dip"
    confidence = "Medium"
  } else if (listing.total >= 50 && riskLow) {
    recommendation = "Apply Retail Only"
    confidence = "Medium"
  } else if (listing.total < 40 || risk.level === "EXTREME") {
    recommendation = "Avoid"
    confidence = "High"
  } else {
    recommendation = "Watch — Selective Apply"
    confidence = "Low"
  }

  // Contrarian score (weak listing but strong business)
  const contraryScore = !listingGood && businessGood
    ? Math.round((business.total + management.total) / 2)
    : 0

  // Green flags
  const greens: string[] = [
    ...(management.positives),
    ...(av.label.includes("Confirmation") ? ["Institutional confirmation — anchor + subscription aligned"] : []),
    ...(valuation >= 75 ? [`PE ${d.peRatio}x vs ${d.peerLabel} — attractive valuation`] : []),
    ...(sectorMom >= 80 ? [`${d.sector} sector momentum is strong (${sectorMom}/100)`] : []),
    ...(business.multibaggerProb >= 60 ? [`Multibagger probability ${business.multibaggerProb}% — similar to Kaynes/Netweb profile`] : []),
    ...(d.fcfPositive ? ["FCF positive — self-funded growth"] : []),
  ]

  // Risk flags (combined from all engines)
  const flags: string[] = [
    ...risk.flags,
    ...management.flags,
  ]

  // UI compat
  const issuePrice = d.priceBandHigh || d.priceBandLow || 100
  const gmp = d.gmpPrice || 0
  const eff = regime.gmpEfficiency

  return {
    listingScore: listing.total,
    listingRating: listing.applyRating,
    listingComponents: listing.components,
    businessScore: business.total,
    businessRating: business.longTermRating,
    businessComponents: business.components,
    multibaggerProb: business.multibaggerProb,
    managementScore: management.total,
    managementComponents: management.components,
    managementFlags: management.flags,
    managementPositives: management.positives,
    anchorValidation: av,
    issueStructure: issueSt,
    valuationScore: valuation,
    sectorMomentum: sectorMom,
    regime,
    risk,
    gmpScenario,
    recommendation,
    confidence,
    // UI compat fields
    total: listing.total,
    anchorScore: anchorResult.score,
    anchorComponents: anchorResult as any,
    businessScore_: business.total,
    subscriptionScore: Math.round((listing.components.nii + listing.components.retail + listing.components.qib) / 0.65),
    issueStructureScore: issueSt.score,
    marketRegimeScore: regime.score,
    gmpScore: Math.round(listing.components.gmp / 0.15),
    historicalScore: Math.round((sectorMom + valuation) / 2),
    riskMultiplier: risk.level === "EXTREME" ? 0.6 : risk.level === "HIGH" ? 0.75 : risk.level === "MEDIUM" ? 0.9 : 1.0,
    applyRating: recommendation,
    flags,
    greens,
    bearCase: gmpScenario.bearCase,
    baseCase: gmpScenario.baseCase,
    bullCase: gmpScenario.bullCase,
    listingBuyScore: listing.total,
    listingBuyRating: listing.applyRating,
    contraryScore,
    postListingRating: contraryScore >= 65
      ? "Post-listing accumulation opportunity — buy the dip"
      : "Monitor for base formation",
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// GMP TREND ENGINE (Section 17 of v3.0 spec)
// ─────────────────────────────────────────────────────────────────────────────
export type GmpTrend = "rising" | "stable" | "falling" | "collapsing"

export function classifyGmpTrend(gmpTrend: number[]): { trend: GmpTrend; label: string; color: string } {
  if (!gmpTrend || gmpTrend.length < 2) return { trend:"stable", label:"No trend data", color:"#6b7280" }

  const first = gmpTrend[0]
  const last  = gmpTrend[gmpTrend.length - 1]
  const pct   = first > 0 ? (last - first) / first * 100 : 0

  // Check recent (last 3) for acceleration
  const recent = gmpTrend.slice(-3)
  const recentChange = recent.length >= 2
    ? (recent[recent.length-1] - recent[0]) / Math.abs(recent[0] || 1) * 100
    : 0

  if      (pct >= 20 || recentChange >= 15) return { trend:"rising",    label:"GMP Rising 🟢 — institutional accumulation signal", color:"#15803d" }
  else if (pct >= -5  && pct < 20)          return { trend:"stable",    label:"GMP Stable — base building",                        color:"#1d4ed8" }
  else if (pct >= -30 && pct < -5)          return { trend:"falling",   label:"GMP Falling ⚠ — caution, demand cooling",           color:"#b45309" }
  else                                       return { trend:"collapsing",label:"GMP Collapsing 🔴 — strong avoid signal",            color:"#b91c1c" }
}

// ─────────────────────────────────────────────────────────────────────────────
// OFS INTELLIGENCE ENGINE (Section 9 of v3.0 spec)
// ─────────────────────────────────────────────────────────────────────────────
export type OfsSeller = "founder" | "private_equity" | "vc" | "institution" | "government" | "promoter_group" | "unknown"

export function analyzeOfs(d: IpoData): {
  label: string
  penalty: number
  warning: string
  sellerType: OfsSeller
} {
  const ofs = d.ofsPct ?? 0
  const fresh = d.freshIssuePct ?? 0

  // Infer seller type from context
  let sellerType: OfsSeller = "unknown"
  let extraPenalty = 0
  let warning = ""

  // Government / PSU: OFS is mandatory policy, not a red flag
  const isPsu = d.sector?.toLowerCase().includes("psu") ||
                d.name?.toLowerCase().includes("bharat") ||
                d.name?.toLowerCase().includes("india ltd") ||
                d.name?.toLowerCase().includes("ntpc") ||
                d.name?.toLowerCase().includes("coal")

  if (isPsu) {
    sellerType = "government"
    warning = "PSU divestment — OFS is government policy, not a red flag"
    extraPenalty = 0
  } else if (ofs >= 80 && fresh < 20) {
    // Likely PE/VC exit
    sellerType = "private_equity"
    extraPenalty = 8
    warning = "Heavy PE/VC exit pattern — all capital going to sellers, none to company"
  } else if (ofs >= 50) {
    sellerType = "promoter_group"
    warning = "Significant promoter exit — review lock-in post-IPO"
  }

  // Base penalty from issue structure
  const basePenalty = fresh >= 70 ? -15
    : fresh >= 50 ? -5
    : ofs >= 90 ? 25
    : ofs >= 70 ? 15
    : 0

  const label = ofs === 0 ? "100% Fresh — company raises all capital"
    : fresh >= 70 ? `${fresh}% Fresh Issue — growth capital majority ✅`
    : fresh >= 50 ? `Mixed — ${fresh}% fresh, ${ofs}% OFS`
    : ofs >= 90   ? `⚠ ${ofs}% OFS — investors exiting, company raises nothing`
    : `🔴 ${ofs}% OFS — majority is seller exit`

  return { label, penalty: basePenalty + extraPenalty, warning, sellerType }
}

// ─────────────────────────────────────────────────────────────────────────────
// SUBSCRIPTION MOMENTUM ENGINE (Section 18)
// Tracks subscription acceleration across 3 days
// ─────────────────────────────────────────────────────────────────────────────
export function analyzeSubMomentum(dayData: { day:number; qibX:number; niiX:number; retailX:number; totalX:number }[]): {
  qibAcceleration: "rising" | "stable" | "flat"
  niiAcceleration: "rising" | "stable" | "flat"
  lateInstitutional: boolean
  signal: string
} {
  if (dayData.length < 2) return {
    qibAcceleration:"flat", niiAcceleration:"flat",
    lateInstitutional:false, signal:"Only one day data"
  }

  const first = dayData[0]
  const last  = dayData[dayData.length-1]

  const qibGrowth   = first.qibX > 0 ? (last.qibX - first.qibX) / first.qibX : 0
  const niiGrowth   = first.niiX > 0 ? (last.niiX - first.niiX) / first.niiX : 0
  const qibAcc = qibGrowth >= 0.5 ? "rising" : qibGrowth >= 0.1 ? "stable" : "flat"
  const niiAcc = niiGrowth >= 0.5 ? "rising" : niiGrowth >= 0.1 ? "stable" : "flat"

  // Late institutional = QIB jumps significantly on Day 2 or 3
  const lateQibJump = dayData.length >= 2 && dayData[dayData.length-1].qibX > dayData[0].qibX * 2
  const lateInstitutional = lateQibJump

  const signal = qibAcc === "rising" && niiAcc === "rising" ? "Strong acceleration — institutional + HNI both accelerating"
    : qibAcc === "rising" ? "QIB acceleration — institutional conviction growing"
    : niiAcc === "rising" ? "NII acceleration — HNI demand building"
    : lateInstitutional   ? "Late institutional surge on Day 2/3 — positive signal"
    : "Steady subscription — no unusual acceleration"

  return { qibAcceleration:qibAcc, niiAcceleration:niiAcc, lateInstitutional, signal }
}
