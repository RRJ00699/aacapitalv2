import type {
  DataProvider, Exchange, StockPrice,
  StockFundamentals, StockOwnership, StockTechnicals,
} from "./interface"

function seed(sym: string) {
  return sym.split("").reduce((a, c) => a + c.charCodeAt(0), 0)
}
function r(s: number, min: number, max: number, offset = 0) {
  return +(min + (((s * 17 + offset * 31) % 100) / 100) * (max - min)).toFixed(2)
}
function ri(s: number, min: number, max: number, offset = 0) {
  return Math.round(r(s, min, max, offset))
}
function arr(s: number, min: number, max: number, len = 8) {
  return Array.from({ length: len }, (_, i) => r(s, min, max, i + 10))
}

export class SimulatedProvider implements DataProvider {
  name = "simulated" as const
  tier = "free" as const
  exchanges: Exchange[] = ["NSE", "BSE", "NASDAQ", "NYSE"]

  async isAvailable(): Promise<boolean> { return true }

  async getPrice(symbol: string, _exchange?: any): Promise<StockPrice> {
    const s = seed(symbol)
    const price = r(s, 80, 8500, 1)
    return {
      price,
      change: r(s, -120, 180, 2),
      changePct: r(s, -4, 6, 3),
      dayHigh: +(price * r(s, 1.01, 1.04, 4)).toFixed(2),
      dayLow: +(price * r(s, 0.96, 0.99, 5)).toFixed(2),
      week52h: +(price * r(s, 1.1, 1.6, 6)).toFixed(2),
      week52l: +(price * r(s, 0.5, 0.85, 7)).toFixed(2),
      volume: ri(s, 100000, 5000000, 8),
      timestamp: new Date().toISOString(),
    }
  }

  async getFundamentals(symbol: string, _exchange?: any): Promise<StockFundamentals> {
    const s = seed(symbol)
    const cmp = r(s, 80, 8500, 1)
    const rev = arr(s, 400, 9000, 8)
    const pat = arr(s, 40, 1400, 8)
    const fcf = arr(s, -80, 900, 8)
    const quarters = ["Q1'24","Q2'24","Q3'24","Q4'24","Q1'25","Q2'25","Q3'25","Q4'25"]
    const revCAGR = +((((rev[7] / rev[0]) ** (1/3)) - 1) * 100).toFixed(1)
    const patCAGR = +((((pat[7] / pat[0]) ** (1/3)) - 1) * 100).toFixed(1)
    return {
      pe: r(s, 6, 90, 2),
      pb: r(s, 0.6, 15, 9),
      roe: r(s, 6, 52, 10),
      roce: r(s, 8, 55, 11),
      debtToEquity: r(s, 0.02, 2.2, 12),
      operatingMargin: r(s, 6, 38, 13),
      revenueCAGR3Y: revCAGR,
      patCAGR3Y: patCAGR,
      mcap: +(cmp * r(s, 150, 90000, 14)).toFixed(0),
      quarterlyRevenue: rev,
      quarterlyPAT: pat,
      quarterlyFCF: fcf,
      quarterlyLabels: quarters,
      targetMean: +(cmp * r(s, 1.1, 1.45, 15)).toFixed(0),
      targetHigh: +(cmp * r(s, 1.25, 1.6, 16)).toFixed(0),
      targetLow: +(cmp * r(s, 0.88, 1.08, 17)).toFixed(0),
      analystCount: ri(s, 6, 30, 18),
      buyPct: ri(s, 42, 85, 19),
    }
  }

  async getOwnership(symbol: string, _exchange?: any): Promise<StockOwnership> {
    const s = seed(symbol)
    return {
      promoterPct: r(s, 38, 79, 20),
      pledgePct: r(s, 0, 20, 21),
      fiiHistory: arr(s, 5, 24, 8),
      diiHistory: arr(s, 3, 18, 8),
      mfHistory: arr(s, 2, 15, 8),
      institutionPct: r(s, 20, 65, 22),
    }
  }

  async getTechnicals(symbol: string, _exchange?: any): Promise<StockTechnicals> {
    const s = seed(symbol)
    const cmp = r(s, 80, 8500, 1)
    const ema20 = +(cmp * r(s, 0.93, 1.05, 23)).toFixed(0)
    const ema50 = +(cmp * r(s, 0.87, 1.01, 24)).toFixed(0)
    const ema200 = +(cmp * r(s, 0.76, 0.96, 25)).toFixed(0)
    const rsi = r(s, 30, 78, 26)
    return {
      ema20, ema50, ema200, rsi,
      macd: rsi > 55 ? "Bullish" : rsi < 45 ? "Bearish" : "Neutral",
      atr: +(cmp * 0.022).toFixed(2),
      support1: +(cmp * r(s, 0.93, 0.97, 27)).toFixed(0),
      support2: +(cmp * r(s, 0.87, 0.92, 28)).toFixed(0),
      resist1: +(cmp * r(s, 1.05, 1.10, 29)).toFixed(0),
      resist2: +(cmp * r(s, 1.11, 1.20, 30)).toFixed(0),
      trend: cmp > ema200 ? "Bullish" : "Bearish",
    }
  }
}
