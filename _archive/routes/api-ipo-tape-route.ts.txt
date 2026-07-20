import { NextRequest, NextResponse } from "next/server"
import { computeTapeState, findIpoInstrument, type TapeSnapshot } from "@/lib/ipo/tape"

// In-memory tape state (per session — Phase 2 will use DB)
const tapeStates: Record<string, any> = {}

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const ipoName     = searchParams.get("ipo")
  const symbol      = searchParams.get("symbol")
  const issuePrice  = parseFloat(searchParams.get("issuePrice") || "0")
  const gmpEntry    = parseFloat(searchParams.get("gmpEntry") || "0")
  const listingPrice= parseFloat(searchParams.get("listingPrice") || "0")

  if (!symbol) return NextResponse.json({ error: "symbol required" }, { status: 400 })

  try {
    // Fetch live quote from Kite
    const quoteRes = await fetch(
      `${req.nextUrl.origin}/api/broker/quote?sym=${symbol}&exchange=NSE`
    )

    if (!quoteRes.ok) {
      // Kite not connected — return simulation for demo
      const simSnap = simulateSnapshot(issuePrice, listingPrice, tapeStates[symbol]?.snapshots?.length || 0)
      const state = computeTapeState(
        tapeStates[symbol] || { symbol, ipoName: ipoName || symbol, snapshots: [] },
        simSnap, issuePrice, gmpEntry, listingPrice
      )
      tapeStates[symbol] = state
      return NextResponse.json({ ok: true, state, simulated: true })
    }

    const quote = await quoteRes.json()

    const snap: TapeSnapshot = {
      timestamp:    new Date().toISOString(),
      ltp:          quote.lastPrice,
      open:         quote.open,
      high:         quote.high,
      low:          quote.low,
      volume:       quote.volume,
      vwap:         quote.vwap || quote.lastPrice,
      bidPrice:     quote.bidPrice || quote.lastPrice * 0.999,
      askPrice:     quote.askPrice || quote.lastPrice * 1.001,
      bidQty:       quote.bidQty || 5000,
      askQty:       quote.askQty || 4000,
      bidAskImbalance: 0,
      spreadPct:    0,
      priceVsVwapPct: 0,
    }

    // Compute derived
    const totalQty = snap.bidQty + snap.askQty
    snap.bidAskImbalance  = totalQty > 0 ? snap.bidQty / totalQty : 0.5
    snap.spreadPct        = snap.ltp > 0 ? (snap.askPrice - snap.bidPrice) / snap.ltp * 100 : 0
    snap.priceVsVwapPct   = snap.vwap > 0 ? (snap.ltp - snap.vwap) / snap.vwap * 100 : 0

    const state = computeTapeState(
      tapeStates[symbol] || { symbol, ipoName: ipoName || symbol, snapshots: [] },
      snap, issuePrice, gmpEntry, listingPrice
    )
    tapeStates[symbol] = state

    return NextResponse.json({ ok: true, state, simulated: false })
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}

// Demo simulation when Kite not connected
function simulateSnapshot(issuePrice: number, listingPrice: number, tick: number): TapeSnapshot {
  const base = listingPrice || issuePrice * 1.15
  const drift = Math.sin(tick * 0.3) * base * 0.008 + (Math.random() - 0.48) * base * 0.005
  const ltp = Math.round((base + drift) * 100) / 100
  const vwap = Math.round((base + drift * 0.3) * 100) / 100
  const bidQty = Math.round(3000 + Math.random() * 4000)
  const askQty = Math.round(2000 + Math.random() * 4000)
  const totalQty = bidQty + askQty
  const spreadAmt = ltp * 0.001
  return {
    timestamp:       new Date().toISOString(),
    ltp, open: base, high: ltp * 1.003, low: ltp * 0.997,
    volume:          Math.round(100000 + tick * 8000 + Math.random() * 20000),
    vwap,
    bidPrice:        ltp - spreadAmt / 2,
    askPrice:        ltp + spreadAmt / 2,
    bidQty, askQty,
    bidAskImbalance: totalQty > 0 ? bidQty / totalQty : 0.5,
    spreadPct:       spreadAmt / ltp * 100,
    priceVsVwapPct:  vwap > 0 ? (ltp - vwap) / vwap * 100 : 0,
  }
}
