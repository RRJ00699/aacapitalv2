import type {
  DataProvider, Exchange, StockPrice,
  StockFundamentals, StockOwnership, StockTechnicals,
} from "./interface"

export class NseProvider implements DataProvider {
  name = "nse" as const
  tier = "free" as const
  exchanges: Exchange[] = ["NSE", "BSE"]

  async isAvailable(): Promise<boolean> { return true }

  async getPrice(symbol: string, _exchange?: any): Promise<StockPrice> {
    const { NSE } = await import("nse-bse-api")
    const nse = new NSE(".")
    try {
      const data: any = await nse.equityQuote(symbol)
      await nse.exit()

      const price = data?.priceInfo?.lastPrice ?? data?.lastPrice ?? 0
      const prev = data?.priceInfo?.previousClose ?? data?.previousClose ?? price
      const change = data?.priceInfo?.change ?? (price - prev)
      const pChange = data?.priceInfo?.pChange ?? (prev > 0 ? ((price - prev) / prev) * 100 : 0)

      if (!price) throw new Error(`No price data for ${symbol}`)

      return {
        price: +price.toFixed(2),
        change: +change.toFixed(2),
        changePct: +pChange.toFixed(2),
        dayHigh: data?.priceInfo?.intraDayHighLow?.max ?? data?.dayHigh ?? price,
        dayLow: data?.priceInfo?.intraDayHighLow?.min ?? data?.dayLow ?? price,
        week52h: data?.priceInfo?.weekHighLow?.max ?? data?.week52High ?? 0,
        week52l: data?.priceInfo?.weekHighLow?.min ?? data?.week52Low ?? 0,
        volume: data?.securityInfo?.tradedVolume ?? data?.totalTradedVolume ?? 0,
        timestamp: new Date().toISOString(),
      }
    } catch (e) {
      try { await nse.exit() } catch {}
      throw e
    }
  }

  async getFundamentals(symbol: string, _exchange?: any): Promise<StockFundamentals> {
    const { NSE } = await import("nse-bse-api")
    const nse = new NSE(".")
    try {
      const data: any = await nse.equityQuote(symbol)
      await nse.exit()
      return {
        pe: data?.metadata?.pdSymbolPe ?? null,
        pb: null, roe: null, roce: null,
        debtToEquity: null, operatingMargin: null,
        revenueCAGR3Y: null, patCAGR3Y: null,
        mcap: null,
        quarterlyRevenue: [], quarterlyPAT: [],
        quarterlyFCF: [], quarterlyLabels: [],
        targetMean: null, targetHigh: null,
        targetLow: null, analystCount: null, buyPct: null,
      }
    } catch {
      try { await nse.exit() } catch {}
      throw new Error(`No fundamentals for ${symbol}`)
    }
  }

  async getOwnership(symbol: string, _exchange?: any): Promise<StockOwnership> {
    return {
      promoterPct: null, pledgePct: null,
      fiiHistory: [], diiHistory: [], mfHistory: [],
      institutionPct: null,
    }
  }

  async getTechnicals(symbol: string, _exchange?: any): Promise<StockTechnicals> {
    const { NSE } = await import("nse-bse-api")
    const nse = new NSE(".")
    try {
      const end = new Date()
      const start = new Date(Date.now() - 365 * 24 * 60 * 60 * 1000)
      const data = await nse.historical.fetchEquityHistoricalData({
        symbol,
        from_date: start,
        to_date: end,
      })
      await nse.exit()

      const rows: any[] = (data as any)?.data ?? data ?? []
      if (!rows.length || rows.length < 20) throw new Error("Not enough history")

      const closes = rows
        .map((r: any) => parseFloat(r.CH_CLOSING_PRICE ?? r.close ?? r.lastPrice ?? 0))
        .filter((v: number) => v > 0)
        .reverse() // oldest first

      const ema = (prices: number[], period: number): number | null => {
        if (prices.length < period) return null
        const k = 2 / (period + 1)
        let val = prices.slice(0, period).reduce((a, b) => a + b) / period
        for (let i = period; i < prices.length; i++) val = prices[i] * k + val * (1 - k)
        return +val.toFixed(2)
      }

      const calcRsi = (prices: number[], period = 14): number | null => {
        if (prices.length < period + 1) return null
        let gains = 0, losses = 0
        for (let i = 1; i <= period; i++) {
          const diff = prices[i] - prices[i - 1]
          if (diff > 0) gains += diff; else losses -= diff
        }
        return +(100 - 100 / (1 + gains / (losses || 1))).toFixed(2)
      }

      const e20 = ema(closes, 20)
      const e50 = ema(closes, 50)
      const e200 = ema(closes, 200)
      const rsiVal = calcRsi(closes)
      const last = closes[closes.length - 1]

      return {
        ema20: e20, ema50: e50, ema200: e200, rsi: rsiVal,
        macd: rsiVal && rsiVal > 55 ? "Bullish" : rsiVal && rsiVal < 45 ? "Bearish" : "Neutral",
        atr: null,
        support1: e20 ? +(e20 * 0.97).toFixed(2) : null,
        support2: e50 ? +(e50 * 0.95).toFixed(2) : null,
        resist1: last ? +(last * 1.05).toFixed(2) : null,
        resist2: last ? +(last * 1.10).toFixed(2) : null,
        trend: e200 && last ? (last > e200 ? "Bullish" : "Bearish") : null,
      }
    } catch {
      try { await nse.exit() } catch {}
      throw new Error(`No technicals for ${symbol}`)
    }
  }
}
