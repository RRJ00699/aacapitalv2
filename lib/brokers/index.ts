import { ZerodhaProvider } from "./zerodha"
import type { BrokerAdapter as BrokerProvider } from "./interface"

// Get the active broker — switchable via env
export function getBroker(): BrokerProvider {
  const broker = process.env.ACTIVE_BROKER || "zerodha"
  switch (broker) {
    case "zerodha": return new ZerodhaProvider()
    // Future: case "icici": return new ICICIProvider()
    // Future: case "groww": return new GrowwProvider()
    default: return new ZerodhaProvider()
  }
}

export { ZerodhaProvider }
export type { BrokerProvider }
