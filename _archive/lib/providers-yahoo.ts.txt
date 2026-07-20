import type {
  DataProvider, Exchange, StockPrice,
  StockFundamentals, StockOwnership, StockTechnicals,
} from "./interface"

// Free Yahoo Finance — no API key needed
const YF_BASE = "https://query1.finance.yahoo.com"
const YF_HEADERS = {
  "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
  "Accept": "application/json",
}

function toYahooSymbol(symbol: string, exchange: Exchange): string {
  if (exchange === "NSE") return `${symbol}.NS`
  if (exchange === "BSE") return `${symbol}.BO`
  return symbol
}

async function fetchYF(path: string) {
  const res = await fetch(`${YF_BASE}${path}`, {
    headers: YF_HEADERS,
    next: { revalidate: 300 },
  })
  if (!res.ok) throw new Error(`YF API ${res.status}`)
  return res.json()
}

export class YahooProvider implements DataProvider {
  name = "yahoo" as const
  tier = "free" as const
  exchanges: Exchange[] = ["NSE", "BSE", "NASDAQ", "NYSE"]

  async isAvailable(): Promise<boolean> { return true }

  async getPrice(symbol: string, exchange: Exchange): Promise<StockPrice> {
    const ySym = toYahooSymbol(symbol, exchange)
    const data = await fetchYF(`/v8/finance/chart/${ySym}?interval=1d&range=1d`)
    const meta = data?.chart?.result?.[0]?.meta
    if (!meta?.regularMarketPrice) throw new Error(`No price for ${symbol}`)
    const prev = meta.previousClose ?? meta.chartPreviousClose ?? meta.regularMarketPrice
    return {
      price: +meta.regularMarketPrice.toFixed(2),
      change: +(meta.regularMarketPrice - prev).toFixed(2),
      changePct: +(((meta.regularMarketPrice - prev) / prev) * 100).toFixed(2),
      dayHigh: meta.regularMarketDayHigh ?? meta.regularMarketPrice,
      dayLow: meta.regularMarketDayLow ?? meta.regularMarketPrice,
      week52h: meta.fiftyTwoWeekHigh ?? 0,
      week52l: meta.fiftyTwoWeekLow ?? 0,
      volume: meta.regularMarketVolume ?? 0,
      timestamp: new Date().toISOString(),
    }
  }

  async getFundamentals(symbol: string, exchange: Exchange): Promise<StockFundamentals> {
    const ySym = toYahooSymbol(symbol, exchange)
    try {
      const data = await fetchYF(
        `/v10/finance/quoteSummary/${ySym}?modules=summaryDetail,financialData,defaultKeyStatistics,incomeStatementHistory`
      )
      const r = data?.quoteSummary?.result?.[0] ?? {}
      const sd = r.summaryDetail ?? {}
      const fd = r.financialData ?? {}
      const ks = r.defaultKeyStatistics ?? {}
      const inc = r.incomeStatementHistory?.incomeStatementHistory ?? []

      const raw = (o: any) => o?.raw ?? o ?? null
      const pct = (o: any) => o?.raw != null ? +(o.raw * 100).toFixed(2) : o ? +(o * 100).toFixed(2) : null

      const revenues = inc.slice(0,8).map((q: any) => raw(q?.totalRevenue) ?? 0).reverse()
      const pats = inc.slice(0,8).map((q: any) => raw(q?.netIncome) ?? 0).reverse()

      // Calculate 3Y CAGR from income statement
      let revCAGR = null, patCAGR = null
      if (revenues.length >= 4 && revenues[0] > 0 && revenues[revenues.length-1] > 0) {
        revCAGR = +((((revenues[revenues.length-1]/revenues[0])**(1/(revenues.length-1)))-1)*100).toFixed(1)
        patCAGR = pats[0] > 0 ? +((((pats[pats.length-1]/pats[0])**(1/(pats.length-1)))-1)*100).toFixed(1) : null
      }

      return {
        pe: raw(sd.trailingPE),
        pb: raw(ks.priceToBook),
        roe: pct(fd.returnOnEquity),
        roce: null,
        debtToEquity: raw(fd.debtToEquity),
        operatingMargin: pct(fd.operatingMargins),
        revenueCAGR3Y: revCAGR,
        patCAGR3Y: patCAGR,
        mcap: raw(sd.marketCap),
        quarterlyRevenue: revenues,
        quarterlyPAT: pats,
        quarterlyFCF: [],
        quarterlyLabels: inc.slice(0,8).map((_:any,i:number) => `FY${24-i}`).reverse(),
        targetMean: raw(fd.targetMeanPrice),
        targetHigh: raw(fd.targetHighPrice),
        targetLow: raw(fd.targetLowPrice),
        analystCount: raw(fd.numberOfAnalystOpinions),
        buyPct: null,
      }
    } catch {
      throw new Error(`No fundamentals for ${symbol}`)
    }
  }

  async getOwnership(symbol: string, exchange: Exchange): Promise<StockOwnership> {
    return {
      promoterPct: null, pledgePct: null,
      fiiHistory: [], diiHistory: [], mfHistory: [],
      institutionPct: null,
    }
  }

  async getTechnicals(symbol: string, exchange: Exchange): Promise<StockTechnicals> {
    const ySym = toYahooSymbol(symbol, exchange)
    try {
      const data = await fetchYF(`/v8/finance/chart/${ySym}?interval=1d&range=1y`)
      const closes: number[] = data?.chart?.result?.[0]?.indicators?.quote?.[0]?.close ?? []
      const valid = closes.filter((c: number) => c != null && !isNaN(c))
      if (valid.length < 20) throw new Error("Not enough history")

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

      const e20 = ema(valid, 20)
      const e50 = ema(valid, 50)
      const e200 = ema(valid, 200)
      const rsiVal = calcRsi(valid)
      const last = valid[valid.length - 1]

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
      throw new Error(`No technicals for ${symbol}`)
    }
  }
}
