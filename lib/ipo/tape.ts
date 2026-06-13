// ─────────────────────────────────────────────────────────────────────────────
// AACapital Live Tape Engine — Phase 1
// Uses Zerodha Kite Quote API (30s polling) as Phase 1
// Foundation for WebSocket upgrade in Phase 2
// ─────────────────────────────────────────────────────────────────────────────

export interface TapeSnapshot {
  timestamp: string
  ltp: number
  open: number
  high: number
  low: number
  volume: number
  vwap: number          // from Kite
  bidPrice: number
  askPrice: number
  bidQty: number
  askQty: number
  // Computed
  bidAskImbalance: number      // bid_qty / (bid_qty + ask_qty)
  spreadPct: number            // (ask - bid) / ltp * 100
  priceVsVwapPct: number       // (ltp - vwap) / vwap * 100
}

export interface TapeState {
  symbol: string
  ipoName: string
  issuePrice: number
  gmpEntryPrice: number
  listingPrice: number

  snapshots: TapeSnapshot[]

  // Derived
  first5MinHigh: number | null
  first5MinLow: number | null
  openingRangeBreakout: boolean
  openingRangeBreakdown: boolean
  volumeVelocity: number        // current 1-min vol vs avg 1-min vol

  // Signals
  profitBookingSignals: string[]
  continuationSignals: string[]
  profitBookingProb: number    // 0-100
  continuationProb: number     // 0-100

  // Score
  liveTapeScore: number
  action: TapeAction
  actionColor: "green" | "amber" | "red"

  // Phase 2 placeholder
  depth5: null  // populated in Phase 2 WebSocket
  depth20: null // populated in Phase 2 WebSocket
}

export type TapeAction =
  | "HOLD / TRAIL / ADD ABOVE HIGH"
  | "HOLD WITH VWAP STOP"
  | "BOOK PARTIAL / WAIT"
  | "EXIT WEAK POSITION"
  | "HARD EXIT / NO AVERAGING"

// ─────────────────────────────────────────────────────────────────────────────
// Core computation
// ─────────────────────────────────────────────────────────────────────────────
export function computeTapeState(
  prev: Partial<TapeState>,
  snap: TapeSnapshot,
  issuePrice: number,
  gmpEntryPrice: number,
  listingPrice: number,
  niftyTrendUp: boolean = true
): TapeState {
  const snapshots = [...(prev.snapshots || []), snap].slice(-120) // keep 2 hrs of 1-min snaps

  // First 5 minute range (first 5 snapshots if polling every 60s)
  const first5 = snapshots.slice(0, 5)
  const first5MinHigh = first5.length >= 3 ? Math.max(...first5.map(s => s.high)) : null
  const first5MinLow  = first5.length >= 3 ? Math.min(...first5.map(s => s.low))  : null

  const orb = first5MinHigh !== null && snap.ltp > first5MinHigh
  const ord = first5MinLow  !== null && snap.ltp < first5MinLow

  // Volume velocity: current snapshot volume vs avg of last 10
  const recent = snapshots.slice(-10)
  const avgVol = recent.length > 0 ? recent.reduce((a,s) => a + s.volume, 0) / recent.length : snap.volume
  const volVelocity = avgVol > 0 ? snap.volume / avgVol : 1.0

  // Profit booking signals
  const profitBookingSignals: string[] = []
  if (snap.ltp < snap.vwap)                           profitBookingSignals.push("LTP below VWAP")
  if (snap.bidQty > 0 && snap.askQty / snap.bidQty > 1.5) profitBookingSignals.push("Ask/Bid ratio > 1.5 — supply pressure")
  if (snapshots.length >= 3) {
    const prev2 = snapshots[snapshots.length - 2]
    const prev1 = snapshots[snapshots.length - 1]
    if (prev1.high < prev2.high && snap.high < prev1.high) profitBookingSignals.push("Lower highs forming")
  }
  if (volVelocity > 1.5 && snap.ltp < snap.vwap)     profitBookingSignals.push("High volume below VWAP")

  // Continuation signals
  const continuationSignals: string[] = []
  if (snap.ltp > snap.vwap)                           continuationSignals.push("LTP above VWAP")
  if (snap.bidQty > 0 && snap.bidQty / snap.askQty > 1.5) continuationSignals.push("Bid/Ask ratio > 1.5 — demand")
  if (orb)                                             continuationSignals.push("Opening range breakout")
  if (volVelocity > 1.3 && snap.ltp > snap.vwap)     continuationSignals.push("Volume acceleration above VWAP")
  if (snapshots.length >= 3) {
    const pullback = snapshots.slice(-3)
    const pulledToVwap = pullback.some(s => Math.abs(s.ltp - s.vwap) / s.vwap < 0.005)
    const thenRallied  = snap.ltp > pullback[0].ltp
    if (pulledToVwap && thenRallied)                  continuationSignals.push("VWAP pullback held — continuation")
  }

  // GMP vs actual listing gap
  const gmpExpected = gmpEntryPrice > issuePrice ? gmpEntryPrice : issuePrice * 1.10
  const listingVsGmp = listingPrice > 0 && gmpExpected > 0
    ? (listingPrice - gmpExpected) / gmpExpected * 100 : 0

  // ── LIVE TAPE SCORE (5 factors, 100 points) ─────────────────────────────
  // 1. Price vs VWAP (25%)
  const pvwap = snap.priceVsVwapPct
  const pvwapScore = pvwap >= 2 ? 25 : pvwap >= 0.5 ? 20 : pvwap >= 0 ? 14 : pvwap >= -1 ? 8 : 2

  // 2. Bid/Ask Imbalance (25%)
  const imb = snap.bidAskImbalance
  const imbScore = imb >= 0.65 ? 25 : imb >= 0.55 ? 20 : imb >= 0.50 ? 14 : imb >= 0.40 ? 8 : 3

  // 3. Volume Velocity (20%)
  const velScore = volVelocity >= 2.0 && snap.ltp > snap.vwap ? 20
    : volVelocity >= 1.5 && snap.ltp > snap.vwap ? 16
    : volVelocity >= 1.0 ? 12
    : volVelocity < 0.5 ? 4 : 8

  // 4. Opening Range (15%)
  const orScore = orb ? 15 : ord ? 0 : first5MinHigh === null ? 8 : 8

  // 5. GMP vs Actual (10%)
  const gmpScore = listingVsGmp >= 5 ? 10 : listingVsGmp >= 0 ? 8 : listingVsGmp >= -5 ? 5 : 2

  // 6. Market trend (5%)
  const mktScore = niftyTrendUp ? 5 : 2

  const liveTapeScore = Math.round(pvwapScore + imbScore + velScore + orScore + gmpScore + mktScore)

  // Probabilities
  const profitBookingProb = Math.round(
    (profitBookingSignals.length / 4) * 70 +
    Math.max(0, -pvwap * 3) +
    Math.max(0, (0.5 - imb) * 40)
  )
  const continuationProb = Math.round(
    (continuationSignals.length / 4) * 70 +
    Math.max(0, pvwap * 3) +
    Math.max(0, (imb - 0.5) * 40)
  )

  // Action
  let action: TapeAction
  if      (liveTapeScore >= 80) action = "HOLD / TRAIL / ADD ABOVE HIGH"
  else if (liveTapeScore >= 65) action = "HOLD WITH VWAP STOP"
  else if (liveTapeScore >= 50) action = "BOOK PARTIAL / WAIT"
  else if (liveTapeScore >= 35) action = "EXIT WEAK POSITION"
  else                           action = "HARD EXIT / NO AVERAGING"

  const actionColor = liveTapeScore >= 65 ? "green" : liveTapeScore >= 50 ? "amber" : "red"

  return {
    symbol: prev.symbol || "",
    ipoName: prev.ipoName || "",
    issuePrice, gmpEntryPrice, listingPrice,
    snapshots,
    first5MinHigh, first5MinLow,
    openingRangeBreakout: orb,
    openingRangeBreakdown: ord,
    volumeVelocity: +volVelocity.toFixed(2),
    profitBookingSignals, continuationSignals,
    profitBookingProb: Math.min(100, profitBookingProb),
    continuationProb:  Math.min(100, continuationProb),
    liveTapeScore: Math.min(100, Math.max(0, liveTapeScore)),
    action, actionColor,
    depth5: null, depth20: null,
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Find IPO instrument token from Kite instruments list
// Called once per listing morning
// ─────────────────────────────────────────────────────────────────────────────
export async function findIpoInstrument(ipoName: string, accessToken: string, apiKey: string): Promise<{ token: string; symbol: string } | null> {
  try {
    const res = await fetch("https://api.kite.trade/instruments/NSE", {
      headers: { "X-Kite-Version":"3", "Authorization":`token ${apiKey}:${accessToken}` }
    })
    if (!res.ok) return null
    const text = await res.text()
    const lines = text.split("\n").slice(1) // skip header
    const words = ipoName.toLowerCase().split(/[\s(]+/).filter(w => w.length >= 4)

    for (const line of lines) {
      const cols = line.split(",")
      if (cols.length < 9) continue
      const symbol = cols[2]?.replace(/"/g, "")
      const name   = cols[8]?.toLowerCase().replace(/"/g, "") || ""
      if (words.some(w => name.includes(w) || symbol?.toLowerCase().includes(w))) {
        return { token: cols[0]?.replace(/"/g, ""), symbol }
      }
    }
    return null
  } catch { return null }
}
