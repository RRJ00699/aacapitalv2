import { NextRequest, NextResponse } from "next/server"
import { findStock, detectExchange } from "@/lib/constants/stocks"
import { getBroker } from "@/lib/brokers"
import { YahooProvider } from "@/lib/providers/yahoo"
import { SimulatedProvider } from "@/lib/providers/simulated"
import { getRealStockData } from "@/lib/realStockData"
import type { Exchange } from "@/lib/providers/interface"

// ── Technical calculation functions ──────────────────────────────────────────

function calcEMA(prices: number[], period: number): number | null {
  if (prices.length < period) return null
  const k = 2 / (period + 1)
  let val = prices.slice(0, period).reduce((a, b) => a + b) / period
  for (let i = period; i < prices.length; i++) val = prices[i] * k + val * (1 - k)
  return +val.toFixed(2)
}

function calcRSI(prices: number[], period = 14): number | null {
  if (prices.length < period + 1) return null
  let gains = 0, losses = 0
  for (let i = prices.length - period; i < prices.length; i++) {
    const diff = prices[i] - prices[i - 1]
    if (diff > 0) gains += diff; else losses -= diff
  }
  const rs = gains / (losses || 0.001)
  return +(100 - 100 / (1 + rs)).toFixed(2)
}

function calcATR(candles: any[], period = 14): number {
  if (candles.length < period + 1) return 0
  const trs = candles.slice(-period - 1).map((c: any, i: number, arr: any[]) => {
    if (i === 0) return +c.high - +c.low
    const prev = arr[i - 1]
    return Math.max(
      +c.high - +c.low,
      Math.abs(+c.high - +prev.close),
      Math.abs(+c.low  - +prev.close)
    )
  })
  return +(trs.slice(-period).reduce((a, b) => a + b, 0) / period).toFixed(2)
}

function calcPivotPoints(candle: any) {
  const h = +candle.high, l = +candle.low, c = +candle.close
  const pivot = +((h + l + c) / 3).toFixed(2)
  return {
    pivot,
    r1: +(2 * pivot - l).toFixed(2),
    r2: +(pivot + (h - l)).toFixed(2),
    r3: +(h + 2 * (pivot - l)).toFixed(2),
    s1: +(2 * pivot - h).toFixed(2),
    s2: +(pivot - (h - l)).toFixed(2),
    s3: +(l - 2 * (h - pivot)).toFixed(2),
  }
}

function calcBuyZone(atr: number, pivots: any, ema20: number | null, currentPrice: number) {
  const s1 = pivots.s1
  const s2 = pivots.s2
  return {
    idealEntry:   +(s1).toFixed(2),
    entryZoneLow: +(s1 - atr * 0.3).toFixed(2),
    entryZoneHigh:+(s1 + atr * 0.3).toFixed(2),
    stopLoss:     +(s2 - atr * 0.2).toFixed(2),
    stopLossPct:  currentPrice > 0 ? +((s2 - atr * 0.2 - currentPrice) / currentPrice * 100).toFixed(1) : -8,
    target1:      +pivots.r1.toFixed(2),
    target2:      +pivots.r2.toFixed(2),
    target3:      +pivots.r3.toFixed(2),
    target1Pct:   currentPrice > 0 ? +((pivots.r1 - currentPrice) / currentPrice * 100).toFixed(1) : 8,
    target2Pct:   currentPrice > 0 ? +((pivots.r2 - currentPrice) / currentPrice * 100).toFixed(1) : 15,
    riskReward:   atr > 0 ? +((pivots.r1 - currentPrice) / Math.abs(s2 - currentPrice || 1)).toFixed(2) : 0,
  }
}

function isNR7(candles: any[]): boolean {
  if (candles.length < 7) return false
  const ranges = candles.slice(-7).map((c: any) => +c.high - +c.low)
  return ranges[ranges.length - 1] === Math.min(...ranges)
}

function calcVolumeRatio(candles: any[]): number {
  if (candles.length < 11) return 1
  const last     = +candles[candles.length - 1].volume
  const avg10    = candles.slice(-11, -1).reduce((a: number, c: any) => a + +c.volume, 0) / 10
  return avg10 > 0 ? +(last / avg10).toFixed(2) : 1
}

function classifyTrend(ema20: number | null, ema50: number | null, ema200: number | null, price: number): string {
  if (!ema20 || !ema50 || !ema200) return "Unknown"
  if (price > ema20 && ema20 > ema50 && ema50 > ema200) return "Strong Uptrend"
  if (price > ema50 && price > ema200) return "Uptrend"
  if (price < ema20 && ema20 < ema50) return "Downtrend"
  if (price < ema200) return "Below 200 DMA — Bearish"
  return "Sideways"
}

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url)
    const sym = searchParams.get("sym")?.toUpperCase().trim()
    const exchangeParam = searchParams.get("exchange") as Exchange | null
    if (!sym) return NextResponse.json({ error: "Symbol required" }, { status: 400 })

    const meta  = findStock(sym)
    const exch: Exchange = exchangeParam || meta?.exchange || detectExchange(sym)
    const isIndian = exch === "NSE" || exch === "BSE"

    const sim = new SimulatedProvider()
    const [simPrice, simFund, simOwn, simTech] = await Promise.all([
      sim.getPrice(sym, exch),
      sim.getFundamentals(sym, exch),
      sim.getOwnership(sym, exch),
      sim.getTechnicals(sym, exch),
    ])

    let livePrice = null, liveFund = null, liveTech = null, buyZoneData = null
    let source = "simulated"

    if (isIndian) {
      try {
        const broker = getBroker()
        const connected = await broker.isConnected()
        if (connected) {
          const quote = await broker.getQuote(sym, exch)
          livePrice = {
            price: quote.lastPrice,
            change: quote.change,
            changePct: quote.changePct,
            dayHigh: quote.high,
            dayLow: quote.low,
            week52h: 0, week52l: 0,
            volume: quote.volume,
            timestamp: quote.timestamp,
          }

          // 2 years of candles for robust technical analysis
          const to   = new Date().toISOString().split("T")[0]
          const from = new Date(Date.now() - 730 * 24 * 60 * 60 * 1000).toISOString().split("T")[0]
          const candles = await broker.getHistoricalData(sym, exch, from, to, "day")

          if (candles.length >= 20) {
            const closes  = candles.map((c: any) => +c.close)
            const last    = closes[closes.length - 1]
            const e20     = calcEMA(closes, 20)
            const e50     = calcEMA(closes, 50)
            const e200    = calcEMA(closes, 200)
            const rsi     = calcRSI(closes)
            const atr     = calcATR(candles)
            const pivots  = calcPivotPoints(candles[candles.length - 1])
            const volRatio = calcVolumeRatio(candles)
            const nr7     = isNR7(candles)
            const trend   = classifyTrend(e20, e50, e200, last)

            // Week 52 high/low
            const year = candles.slice(-252)
            const w52h = +Math.max(...year.map((c: any) => +c.high)).toFixed(2)
            const w52l = +Math.min(...year.map((c: any) => +c.low)).toFixed(2)
            if (livePrice) { livePrice.week52h = w52h; livePrice.week52l = w52l }

            liveTech = {
              ema20: e20, ema50: e50, ema200: e200, rsi,
              macd: rsi && rsi > 55 ? "Bullish" : rsi && rsi < 45 ? "Bearish" : "Neutral",
              atr,
              // Proper pivot-based support/resistance
              support1: pivots.s1,
              support2: pivots.s2,
              support3: pivots.s3,
              resist1:  pivots.r1,
              resist2:  pivots.r2,
              resist3:  pivots.r3,
              pivot:    pivots.pivot,
              trend,
              volumeRatio: volRatio,
              isNR7: nr7,
            }

            // Buy zone analysis
            if (e20) {
              buyZoneData = {
                ...calcBuyZone(atr, pivots, e20, last),
                atr,
                trend,
                volumeSignal: volRatio > 1.5 ? "High volume — strong signal" : volRatio > 1.2 ? "Above average volume" : "Normal volume",
                nr7Signal: nr7 ? "NR7 pattern — potential breakout setup. Watch for volume expansion." : null,
                positionSize: {
                  conservative: +(last * 0.5 / atr).toFixed(0),  // 0.5R position
                  standard:     +(last * 1.0 / atr).toFixed(0),  // 1R position
                  aggressive:   +(last * 1.5 / atr).toFixed(0),  // 1.5R position
                }
              }
            }
          }
          source = "zerodha"
        }
      } catch {}

      if (!livePrice) {
        try {
          const yahoo = new YahooProvider()
          const [p, t] = await Promise.allSettled([
            yahoo.getPrice(sym, exch),
            yahoo.getTechnicals(sym, exch),
          ])
          if (p.status === "fulfilled") { livePrice = p.value; source = "yahoo" }
          if (t.status === "fulfilled") liveTech = t.value
        } catch {}
      }
    } else {
      try {
        const yahoo = new YahooProvider()
        const [p, f, t] = await Promise.allSettled([
          yahoo.getPrice(sym, exch),
          yahoo.getFundamentals(sym, exch),
          yahoo.getTechnicals(sym, exch),
        ])
        if (p.status === "fulfilled") { livePrice = p.value; source = "yahoo" }
        if (f.status === "fulfilled") liveFund = f.value
        if (t.status === "fulfilled") liveTech = t.value
      } catch {}
    }

    // Real Neon data (stock_fundamentals + shareholding_history) — overrides sim/Yahoo.
    const { realFund, realOwn } = await getRealStockData(sym)

    const price       = livePrice || simPrice
    const fundamentals = { ...simFund, ...(liveFund ? Object.fromEntries(Object.entries(liveFund).filter(([_, v]) => v !== null)) : {}), ...realFund }
    const technicals  = liveTech?.ema20 ? liveTech : simTech

    const sourceLabels: Record<string, string> = {
      zerodha:   "✅ Live from Zerodha",
      yahoo:     "✅ Live from Yahoo Finance",
      simulated: "⚠ Simulated — Connect Zerodha for live prices",
    }

    return NextResponse.json({
      ok: true, sym, exch,
      name:     meta?.name || sym,
      sector:   meta?.sector || null,
      index:    meta?.index || [],
      symbol:   sym,
      exchange: exch,
      price, fundamentals,
      ownership:  realOwn ?? simOwn,
      technicals,
      buyZone:    buyZoneData,
      source,
      ownershipReal:    realOwn != null,
      fundamentalsReal: Object.keys(realFund).length > 0,
      dataNote:   sourceLabels[source] || "⚠ Simulated",
      fetchedAt:  new Date().toISOString(),
    })
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}
