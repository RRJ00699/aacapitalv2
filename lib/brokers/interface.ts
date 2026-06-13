export interface BrokerProfile {
  userId:   string
  userName: string
  email:    string
  broker:   string
}

export interface BrokerFunds {
  available: number
  used:      number
  total:     number
  currency?: string
}

export interface BrokerHolding {
  symbol:        string
  exchange:      string
  quantity:      number
  avgPrice:      number
  lastPrice:     number
  pnl:           number
  pnlPct:        number
  currentValue:  number
  investedValue: number
}

export interface BrokerPosition {
  symbol:    string
  exchange:  string
  quantity:  number
  avgPrice:  number
  lastPrice: number
  pnl:       number
  product:   string
  side:      string
}

export interface BrokerOrder {
  orderId:   string
  symbol:    string
  exchange:  string
  quantity:  number
  price:     number
  status:    string
  side:      string
  product:   string
  timestamp: string | Date
}

export interface BrokerQuote {
  symbol:    string
  exchange:  string
  lastPrice: number
  change:    number
  changePct: number
  open:      number
  high:      number
  low:       number
  close:     number
  volume:    number
  timestamp: string | Date
}

export interface BrokerCandle {
  timestamp: string | Date
  open:      number
  high:      number
  low:       number
  close:     number
  volume:    number
}

export interface PlaceOrderParams {
  symbol:     string
  exchange:   string
  side:       "BUY" | "SELL"
  orderType:  string
  quantity:   number
  product:    string
  price?:     number
  validity?:  string
  tag?:       string
}

export interface BrokerProvider {
  name: string
  getLoginUrl(): string
  isConnected(): Promise<boolean>
  getProfile?(): Promise<BrokerProfile>
  getFunds(): Promise<BrokerFunds>
  getHoldings(): Promise<BrokerHolding[]>
  getPositions(): Promise<BrokerPosition[]>
  getOrders(): Promise<BrokerOrder[]>
  getQuote(symbol: string, exchange?: string): Promise<BrokerQuote>
  getHistoricalData(symbol: string, exchange: string, from: string, to: string, interval?: string): Promise<BrokerCandle[]>
  placeOrder(params: PlaceOrderParams): Promise<string>
  cancelOrder(orderId: string): Promise<boolean>
}

export type BrokerAdapter = BrokerProvider

export type Tier = "free" | "pro" | "premium" | "institutional"

export const FEATURES: Record<string, Tier> = {
  "ipo.listing-score":        "free",
  "ipo.gmp":                  "free",
  "ipo.listing-prediction":   "free",
  "ipo.anchor-intelligence":  "pro",
  "ipo.dna-engine":           "pro",
  "ipo.ai-memo":              "pro",
  "ipo.risk-engine":          "pro",
  "ipo.drhp-scanner":         "pro",
  "ipo.live-tape":            "premium",
  "ipo.opportunity-monitor":  "premium",
  "ipo.smart-money":          "premium",
  "ipo.lockin-tracker":       "premium",
  "ipo.subscription-tracker": "premium",
  "api.access":               "institutional",
  "watchlists.custom":        "institutional",
  "portfolio.integration":    "institutional",
}

const TIER_LEVEL: Record<Tier, number> = {
  free: 0, pro: 1, premium: 2, institutional: 3
}

export function canAccess(featureKey: string, userTier: Tier): boolean {
  const required = FEATURES[featureKey]
  if (!required) return true
  return TIER_LEVEL[userTier] >= TIER_LEVEL[required]
}