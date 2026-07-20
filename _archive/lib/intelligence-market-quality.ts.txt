export type OperatorRisk = "LOW" | "MEDIUM" | "HIGH"
export type InvestabilityStatus = "INVESTABLE" | "WATCH_ONLY" | "SUPPRESSED"

export interface MarketQualityInput {
  symbol?: string | null
  marketCapCr?: number | null
  price?: number | null
  avgTradedValueCr?: number | null
  volume?: number | null
  avgVolume20?: number | null
  deliveryPct?: number | null
  publicHoldingPct?: number | null
  promoterPledgePct?: number | null
  smartMoneyScore?: number | null
  businessScore?: number | null
  volatilityPct?: number | null
  changePct?: number | null
}

export interface MarketQualityResult {
  investabilityScore: number
  marketQualityScore: number
  operatorRiskScore: number
  operatorRisk: OperatorRisk
  status: InvestabilityStatus
  reasons: string[]
}

const n = (v: unknown, fallback = 0) => {
  const x = Number(v)
  return Number.isFinite(x) ? x : fallback
}

function scoreBand(value: number, good: number, ok: number) {
  if (value >= good) return 100
  if (value >= ok) return 70
  if (value > 0) return 35
  return 50
}

export function calculateMarketQuality(input: MarketQualityInput): MarketQualityResult {
  const marketCap = n(input.marketCapCr)
  const avgValue = n(input.avgTradedValueCr)
  const volume = n(input.volume)
  const avgVolume = n(input.avgVolume20)
  const delivery = n(input.deliveryPct)
  const pledge = n(input.promoterPledgePct)
  const publicHolding = n(input.publicHoldingPct)
  const sm = n(input.smartMoneyScore, 50)
  const biz = n(input.businessScore, 50)
  const vol = n(input.volatilityPct)
  const change = Math.abs(n(input.changePct))

  const reasons: string[] = []
  const volumeSpike = avgVolume > 0 ? volume / avgVolume : 1

  const liquidityScore = Math.round((
    scoreBand(marketCap, 1000, 500) * 0.45 +
    scoreBand(avgValue, 5, 2) * 0.35 +
    (volumeSpike > 8 ? 30 : volumeSpike > 4 ? 60 : 90) * 0.20
  ))

  const ownershipScore = Math.round(
    (publicHolding > 80 ? 35 : publicHolding > 70 ? 55 : 80) * 0.45 +
    (pledge > 20 ? 20 : pledge > 10 ? 45 : pledge > 5 ? 70 : 90) * 0.35 +
    sm * 0.20
  )

  const qualityScore = Math.round(biz * 0.55 + liquidityScore * 0.30 + ownershipScore * 0.15)

  let operatorRiskScore = 0
  if (marketCap > 0 && marketCap < 500) { operatorRiskScore += 25; reasons.push("Market cap below ₹500 Cr") }
  if (avgValue > 0 && avgValue < 2) { operatorRiskScore += 25; reasons.push("Low average traded value") }
  if (delivery > 0 && delivery < 25) { operatorRiskScore += 15; reasons.push("Weak delivery quality") }
  if (publicHolding > 80) { operatorRiskScore += 15; reasons.push("Very high public holding") }
  if (pledge > 10) { operatorRiskScore += 15; reasons.push("Promoter pledge risk") }
  if (volumeSpike > 8) { operatorRiskScore += 20; reasons.push("Abnormal volume spike") }
  if (vol > 12 || change > 18) { operatorRiskScore += 15; reasons.push("Abnormal volatility") }
  operatorRiskScore = Math.min(100, operatorRiskScore)

  const operatorRisk: OperatorRisk = operatorRiskScore >= 55 ? "HIGH" : operatorRiskScore >= 30 ? "MEDIUM" : "LOW"
  const investabilityScore = Math.max(0, Math.min(100, Math.round(qualityScore - operatorRiskScore * 0.55)))
  const status: InvestabilityStatus = operatorRisk === "HIGH" || investabilityScore < 45
    ? "SUPPRESSED"
    : operatorRisk === "MEDIUM" || investabilityScore < 70
    ? "WATCH_ONLY"
    : "INVESTABLE"

  if (!reasons.length) reasons.push("Liquidity and quality checks passed")

  return {
    investabilityScore,
    marketQualityScore: qualityScore,
    operatorRiskScore,
    operatorRisk,
    status,
    reasons,
  }
}
