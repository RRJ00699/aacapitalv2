export type ProviderName = "yahoo" | "nse" | "trendlyne" | "simulated"
export type Exchange = "NSE" | "BSE" | "NASDAQ" | "NYSE"
export type ProviderTier = "free" | "paid"

export interface StockPrice {
  price: number
  change: number
  changePct: number
  dayHigh: number
  dayLow: number
  week52h: number
  week52l: number
  volume: number
  timestamp: string
}

export interface StockFundamentals {
  pe: number | null
  pb: number | null
  roe: number | null
  roce: number | null
  debtToEquity: number | null
  operatingMargin: number | null
  revenueCAGR3Y: number | null
  patCAGR3Y: number | null
  mcap: number | null
  quarterlyRevenue: number[]
  quarterlyPAT: number[]
  quarterlyFCF: number[]
  quarterlyLabels: string[]
  targetMean: number | null
  targetHigh: number | null
  targetLow: number | null
  analystCount: number | null
  buyPct: number | null
}

export interface StockOwnership {
  promoterPct: number | null
  pledgePct: number | null
  fiiHistory: number[]
  diiHistory: number[]
  mfHistory: number[]
  institutionPct: number | null
}

export interface StockTechnicals {
  ema20: number | null
  ema50: number | null
  ema200: number | null
  rsi: number | null
  macd: string | null
  atr: number | null
  support1: number | null
  support2: number | null
  resist1: number | null
  resist2: number | null
  trend: string | null
}

export interface FullStockData {
  symbol: string
  exchange: Exchange
  price: StockPrice | null
  fundamentals: StockFundamentals | null
  ownership: StockOwnership | null
  technicals: StockTechnicals | null
  source: ProviderName
  dataNote?: string
  fetchedAt: string
}

export interface DataProvider {
  name: ProviderName
  tier: ProviderTier
  exchanges: Exchange[]
  getPrice(symbol: string, exchange: Exchange): Promise<StockPrice>
  getFundamentals(symbol: string, exchange: Exchange): Promise<StockFundamentals>
  getOwnership(symbol: string, exchange: Exchange): Promise<StockOwnership>
  getTechnicals(symbol: string, exchange: Exchange): Promise<StockTechnicals>
  isAvailable(): Promise<boolean>
}
