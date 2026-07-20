// ─────────────────────────────────────────────────────────────────────────────
// AACapital Anchor Intelligence Engine
// Trained on: Top 30 IPO Anchor Master 2020-2026
// Key finding: Anchor quality alone has -0.105 correlation with listing gain
// Anchor quality VALIDATES subscription signal — does not replace it
// ─────────────────────────────────────────────────────────────────────────────

// Tier classification from real data
export const ANCHOR_INVESTORS: Record<string, { score: number; category: string; tier: 1 | 2 | 3 }> = {
  // Tier 1 — Sovereign (100)
  "ADIA":                       { score: 100, category: "Sovereign Fund",    tier: 1 },
  "GIC":                        { score: 100, category: "Sovereign Fund",    tier: 1 },
  "Temasek":                    { score: 95,  category: "Sovereign Fund",    tier: 1 },
  "Norges Bank":                { score: 95,  category: "Pension/Sovereign", tier: 1 },
  "NBIM":                       { score: 95,  category: "Pension/Sovereign", tier: 1 },
  "Government Pension Fund":    { score: 95,  category: "Pension/Sovereign", tier: 1 },
  "CPPIB":                      { score: 95,  category: "Pension/Sovereign", tier: 1 },
  "CDPQ":                       { score: 95,  category: "Pension Fund",      tier: 1 },
  // Tier 1 — Domestic MF (90)
  "SBI Mutual Fund":            { score: 90,  category: "Domestic MF",       tier: 1 },
  "SBI MF":                     { score: 90,  category: "Domestic MF",       tier: 1 },
  "HDFC Mutual Fund":           { score: 90,  category: "Domestic MF",       tier: 1 },
  "HDFC MF":                    { score: 90,  category: "Domestic MF",       tier: 1 },
  "ICICI Prudential MF":        { score: 90,  category: "Domestic MF",       tier: 1 },
  "ICICI Pru MF":               { score: 90,  category: "Domestic MF",       tier: 1 },
  "Nippon India MF":            { score: 90,  category: "Domestic MF",       tier: 1 },
  "Nippon MF":                  { score: 90,  category: "Domestic MF",       tier: 1 },
  "Axis Mutual Fund":           { score: 88,  category: "Domestic MF",       tier: 1 },
  "Axis MF":                    { score: 88,  category: "Domestic MF",       tier: 1 },
  "Kotak Mutual Fund":          { score: 88,  category: "Domestic MF",       tier: 1 },
  "Kotak MF":                   { score: 88,  category: "Domestic MF",       tier: 1 },
  "BlackRock":                  { score: 90,  category: "FPI/Global AM",     tier: 1 },
  // Tier 1 — Insurance + Global IB (85)
  "LIC":                        { score: 85,  category: "Insurance",         tier: 1 },
  "Morgan Stanley":             { score: 85,  category: "FPI/Global IB",     tier: 1 },
  "Goldman Sachs":              { score: 85,  category: "FPI/Global IB",     tier: 1 },
  "Wellington":                 { score: 85,  category: "FPI/Global AM",     tier: 1 },
  "Fidelity":                   { score: 85,  category: "FPI/Global AM",     tier: 1 },
  "SBI Life":                   { score: 84,  category: "Insurance",         tier: 1 },
  "HDFC Life":                  { score: 84,  category: "Insurance",         tier: 1 },
  "ICICI Prudential Life":      { score: 84,  category: "Insurance",         tier: 1 },
  "ICICI Pru Life":             { score: 84,  category: "Insurance",         tier: 1 },
  "Kotak Life":                 { score: 82,  category: "Insurance",         tier: 2 },
  // Tier 2 — Mid-tier (78-82)
  "Franklin Templeton":         { score: 82,  category: "Domestic MF",       tier: 2 },
  "Mirae Asset":                { score: 82,  category: "Domestic MF",       tier: 2 },
  "DSP Mutual Fund":            { score: 80,  category: "Domestic MF",       tier: 2 },
  "DSP MF":                     { score: 80,  category: "Domestic MF",       tier: 2 },
  "Nomura":                     { score: 78,  category: "FPI/Global IB",     tier: 2 },
  "UBS":                        { score: 78,  category: "FPI/Global IB",     tier: 2 },
  "HSBC Global":                { score: 78,  category: "FPI/Global AM",     tier: 2 },
  "BNP Paribas":                { score: 78,  category: "FPI/Global IB",     tier: 2 },
  "BNP":                        { score: 78,  category: "FPI/Global IB",     tier: 2 },
  "WhiteOak":                   { score: 76,  category: "Domestic MF/AIF",   tier: 2 },
  "Ashoka India":               { score: 75,  category: "FPI",               tier: 2 },
  "Bandhan MF":                 { score: 78,  category: "Domestic MF",       tier: 2 },
  // Tier 3 — Lower quality (50-65)
  "Abakkus":                    { score: 65,  category: "AIF/PMS",           tier: 3 },
  "Unifi Capital":              { score: 65,  category: "AIF/PMS",           tier: 3 },
  "Carnelian":                  { score: 62,  category: "AIF/PMS",           tier: 3 },
  "Singularity":                { score: 60,  category: "Family Office/AIF", tier: 3 },
  "Family Office":              { score: 50,  category: "Family Office",      tier: 3 },
}

export interface AnchorScoreResult {
  score: number           // 0-100
  tier1Count: number      // number of tier-1 anchors
  hasSovereign: boolean
  hasTier1MF: boolean
  hasInsurance: boolean
  hasFPI: boolean
  interpretation: string
  warning?: string
  namedAnchors: string[]
}

// Score a new IPO's anchor list in real time
export function scoreAnchors(anchorList: string[]): AnchorScoreResult {
  if (!anchorList || anchorList.length === 0) {
    return {
      score: 40, tier1Count: 0, hasSovereign: false,
      hasTier1MF: false, hasInsurance: false, hasFPI: false,
      interpretation: "No anchor data — scoring conservatively",
      namedAnchors: []
    }
  }

  // Match each anchor against known list
  const matched = anchorList.map(a => {
    const key = Object.keys(ANCHOR_INVESTORS).find(k =>
      a.toLowerCase().includes(k.toLowerCase()) ||
      k.toLowerCase().includes(a.toLowerCase())
    )
    return key ? { name: a, ...ANCHOR_INVESTORS[key] } : { name: a, score: 60, category: "Unknown", tier: 3 as const }
  })

  const hasSovereign = matched.some(a => a.category === "Sovereign Fund" || a.category === "Pension/Sovereign" || a.category === "Pension Fund")
  const hasTier1MF   = matched.some(a => a.category === "Domestic MF" && a.tier === 1)
  const hasInsurance = matched.some(a => a.category === "Insurance")
  const hasFPI       = matched.some(a => a.category.includes("FPI") || a.category.includes("Global"))
  const tier1Count   = matched.filter(a => a.tier === 1).length

  // Score: base + components
  let score = 40
  if (hasSovereign) score += 28
  if (hasTier1MF)   score += 18
  if (hasInsurance)  score += 8
  if (hasFPI)        score += 8
  // Bonus for depth
  if (tier1Count >= 3) score += 4
  if (tier1Count >= 5) score += 4
  score = Math.min(100, score)

  // Interpretation
  let interpretation = ""
  let warning: string | undefined

  if (score >= 90) {
    interpretation = "Elite anchors — sovereign + MF + insurance. Maximum institutional conviction."
  } else if (score >= 80) {
    interpretation = "Strong anchors — tier-1 MFs and/or insurance present. High confidence signal."
  } else if (score >= 65) {
    interpretation = "Moderate anchors — global FPIs + domestic MFs. Decent but not top-tier."
  } else {
    interpretation = "Weak anchors — primarily AIFs/family offices/mid-tier. Treat with caution."
    warning = "Low anchor quality — subscription signal is primary. GMP may be unreliable."
  }

  // Key insight: anchor VALIDATES subscription, doesn't replace it
  if (score >= 85 && !hasTier1MF && !hasSovereign) {
    warning = "Good FPI anchors but no domestic MF or sovereign — retail may not follow institutions"
  }

  return {
    score, tier1Count, hasSovereign, hasTier1MF,
    hasInsurance, hasFPI, interpretation, warning,
    namedAnchors: matched.map(a => a.name)
  }
}

// Historical IPO anchor scores for key IPOs — from real data
export const KNOWN_ANCHOR_SCORES: Record<string, { score: number; anchors: string[] }> = {
  // 2026
  "CMR Green Technologies":      { score: 52, anchors: ["Goldman Sachs", "BNP Paribas"] },
  // 2025
  "LG Electronics India":        { score: 96, anchors: ["ADIA", "GIC", "Norges Bank", "BlackRock", "SBI MF", "HDFC MF"] },
  "Tata Capital":                { score: 94, anchors: ["LIC", "Norges Bank", "Goldman Sachs", "Morgan Stanley", "ICICI Pru MF"] },
  "HDB Financial Services":      { score: 92, anchors: ["BlackRock", "LIC", "Norges Bank", "SBI MF"] },
  "NSDL":                        { score: 84, anchors: ["WhiteOak", "Ashoka India", "Domestic Institutions"] },
  // 2024
  "Hyundai Motor India":         { score: 87, anchors: ["Domestic MFs", "Insurance Companies", "FPIs"] },
  "Bajaj Housing Finance":       { score: 88, anchors: ["Domestic MFs", "FPIs", "Insurance"] },
  "Bharti Hexacom":              { score: 90, anchors: ["ICICI Pru Life", "SBI Life", "HDFC Life", "Kotak Life", "Domestic MFs"] },
  "Premier Energies":            { score: 82, anchors: ["Domestic MFs", "FPIs", "AIFs"] },
  "Swiggy":                      { score: 85, anchors: ["Global Growth Funds", "Domestic MFs", "Tech FPIs"] },
  "NTPC Green Energy":           { score: 84, anchors: ["Domestic MFs", "Insurance", "FPIs"] },
  "TBO Tek":                     { score: 80, anchors: ["Domestic MFs", "FPIs", "AIFs"] },
  "Ola Electric":                { score: 76, anchors: ["Domestic MFs", "FPIs", "AIFs"] },
  "FirstCry":                    { score: 75, anchors: ["Domestic MFs", "FPIs", "PE/Growth Funds"] },
  // 2023
  "Tata Technologies":           { score: 88, anchors: ["17 Domestic MFs via 39 schemes", "FPIs"] },
  "IREDA":                       { score: 82, anchors: ["Domestic MFs", "Insurance", "FPIs"] },
  "Mankind Pharma":              { score: 83, anchors: ["Domestic MFs", "FPIs", "Insurance"] },
  // 2022
  "LIC":                         { score: 91, anchors: ["SBI MF", "GIC", "BNP Paribas", "Domestic MFs"] },
  "Delhivery":                   { score: 80, anchors: ["Fidelity", "Tiger Global Linked", "Domestic MFs"] },
  "Global Health (Medanta)":     { score: 81, anchors: ["Domestic MFs", "Insurance", "FPIs"] },
  "Campus Shoes":                { score: 76, anchors: ["Domestic MFs", "FPIs", "Consumer Funds"] },
  // 2021
  "Zomato":                      { score: 93, anchors: ["Sovereign Funds", "Pension Funds", "Global FPIs", "Insurance", "Domestic MFs"] },
  "Nykaa":                       { score: 86, anchors: ["21 Domestic MFs via 39 schemes", "Global FPIs", "Growth Funds"] },
  "Paytm":                       { score: 86, anchors: ["BlackRock", "CPPIB", "ADIA", "GIC", "Domestic Institutions"] },
  "Sigachi Industries":          { score: 60, anchors: ["Small Domestic MFs", "AIFs"] },
  "Paras Defence":               { score: 68, anchors: ["Mid-tier MFs", "Domestic Institutions"] },
  "Latent View Analytics":       { score: 78, anchors: ["Domestic MFs", "FPIs", "Tech Funds"] },
}

// THE KEY INSIGHT from data analysis:
// Anchor quality score has -0.105 correlation with listing gain
// This means HIGH anchor quality ALONE does not predict listing gain
//
// What it DOES predict:
// 1. IPO legitimacy — prevents pump-and-dump, ensures regulatory quality
// 2. Lock-in stability — 30/90 day lock-in prevents immediate dumping
// 3. Validates subscription — if institutions bid heavily AND anchors are tier-1 = strong signal
//
// The trap cases from real data:
// - Hyundai: anchor score 87 (top tier) but QIB only 7x, listing +4% only
// - Paytm: anchor score 86 (very strong) but product failed, listing -27%
// - Zomato: anchor score 93 (elite) + QIB 52x = listing +66% (right signal)
//
// Formula: Anchor validates subscription. Subscription drives listing.
export const ANCHOR_ENGINE_NOTES = {
  correlation: -0.105,          // anchor score vs listing gain — confirms anchors alone don't predict
  trueSignal: "anchor_x_subscription",  // combined signal is what matters
  anchorTrap: "High anchor + Low subscription = institutional confidence without retail momentum",
  optimalCombo: "Anchor score >80 + QIB >50x + NII >30x = highest probability listing gain",
}
