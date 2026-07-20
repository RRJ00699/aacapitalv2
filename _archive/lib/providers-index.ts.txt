import { NseProvider } from "./nse"
import { YahooProvider } from "./yahoo"
import { SimulatedProvider } from "./simulated"
import { detectExchange } from "@/lib/constants/stocks"
import type { DataProvider, Exchange, FullStockData } from "./interface"

function getChain(exchange: Exchange): DataProvider[] {
  if (exchange === "NSE" || exchange === "BSE") {
    return [
      new NseProvider(),      // NSE direct — most accurate for Indian stocks
      new YahooProvider(),    // fallback
      new SimulatedProvider(),
    ]
  }
  return [
    new YahooProvider(),      // Yahoo for US stocks
    new SimulatedProvider(),
  ]
}

async function getBestProvider(exchange: Exchange): Promise<DataProvider> {
  const chain = getChain(exchange)
  for (const provider of chain) {
    try {
      const ok = await provider.isAvailable()
      if (ok) return provider
    } catch { continue }
  }
  return new SimulatedProvider()
}

export async function getFullStockData(
  symbol: string,
  exchangeOverride?: Exchange
): Promise<FullStockData> {
  const exchange = exchangeOverride || detectExchange(symbol)
  const provider = await getBestProvider(exchange)

  const [price, fundamentals, ownership, technicals] = await Promise.allSettled([
    provider.getPrice(symbol, exchange),
    provider.getFundamentals(symbol, exchange),
    provider.getOwnership(symbol, exchange),
    provider.getTechnicals(symbol, exchange),
  ])

  return {
    symbol,
    exchange,
    price: price.status === "fulfilled" ? price.value : null,
    fundamentals: fundamentals.status === "fulfilled" ? fundamentals.value : null,
    ownership: ownership.status === "fulfilled" ? ownership.value : null,
    technicals: technicals.status === "fulfilled" ? technicals.value : null,
    source: provider.name,
    dataNote: provider.name === "simulated"
      ? "Using simulated data"
      : undefined,
    fetchedAt: new Date().toISOString(),
  }
}

export async function getProviderStatus() {
  const chains = {
    NSE: getChain("NSE"),
    NASDAQ: getChain("NASDAQ"),
  }
  const results: any = {}
  for (const [market, chain] of Object.entries(chains)) {
    results[market] = await Promise.all(
      chain.map(async p => ({
        name: p.name,
        tier: p.tier,
        available: await p.isAvailable().catch(() => false),
      }))
    )
  }
  return results
}

export { detectExchange }
