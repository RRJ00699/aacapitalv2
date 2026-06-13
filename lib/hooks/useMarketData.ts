// lib/hooks/useMarketData.ts
// Sprint 11: Auto-refreshes market snapshot if stale (>4 hours)
// Replaces manual Refresh button dependency in command-center.tsx
//
// Usage:
//   import { useMarketData } from "@/lib/hooks/useMarketData"
//   const { snapshot, loading, refresh } = useMarketData()

import { useState, useEffect, useCallback } from "react"

export interface MarketSnapshot {
  id: number
  snapshot_date: string
  last_updated: string
  nifty_price: number
  banknifty_price: number
  vix: number
  pcr: number
  advance_decline_ratio: number
  fii_flow: number
  dii_flow: number
  nifty_vs_20dma: number
  nifty_vs_50dma: number
  nifty_vs_200dma: number
  market_regime: string
  market_risk_score: number
  market_opportunity_score: number
  recommended_exposure: number
  sector_data_json: string
  confidence: string
  notes: string | null
}

const STALE_THRESHOLD_MS = 4 * 60 * 60 * 1000 // 4 hours

function isStale(snapshot: MarketSnapshot | null): boolean {
  if (!snapshot?.last_updated) return true
  const age = Date.now() - new Date(snapshot.last_updated).getTime()
  return age > STALE_THRESHOLD_MS
}

export function useMarketData() {
  const [snapshot, setSnapshot] = useState<MarketSnapshot | null>(null)
  const [loading, setLoading]   = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError]       = useState<string | null>(null)
  const [autoRefreshed, setAutoRefreshed] = useState(false)

  const fetchSnapshot = useCallback(async () => {
    try {
      const res = await fetch("/api/market/live")
      if (!res.ok) throw new Error(`GET failed ${res.status}`)
      const data = await res.json()
      return data.snapshot as MarketSnapshot | null
    } catch (err) {
      throw err
    }
  }, [])

  const postRefresh = useCallback(async () => {
    try {
      const res = await fetch("/api/market/live", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      })
      if (!res.ok) throw new Error(`POST failed ${res.status}`)
      // After POST, re-fetch the snapshot
      const snap = await fetchSnapshot()
      return snap
    } catch (err) {
      throw err
    }
  }, [fetchSnapshot])

  // Manual refresh (called from Refresh button)
  const refresh = useCallback(async () => {
    setRefreshing(true)
    setError(null)
    try {
      const snap = await postRefresh()
      if (snap) setSnapshot(snap)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setRefreshing(false)
    }
  }, [postRefresh])

  // On mount: fetch snapshot, auto-POST if stale
  useEffect(() => {
    let cancelled = false

    async function init() {
      setLoading(true)
      setError(null)
      try {
        const snap = await fetchSnapshot()

        if (cancelled) return

        if (isStale(snap)) {
          // Snapshot is stale — auto-POST silently
          setAutoRefreshed(false)
          try {
            const fresh = await postRefresh()
            if (!cancelled && fresh) {
              setSnapshot(fresh)
              setAutoRefreshed(true)
            }
          } catch {
            // POST failed (e.g. Zerodha not connected) — show stale data anyway
            if (!cancelled) setSnapshot(snap)
          }
        } else {
          if (!cancelled) setSnapshot(snap)
        }
      } catch (err: any) {
        if (!cancelled) setError(err.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    init()
    return () => { cancelled = true }
  }, [fetchSnapshot, postRefresh])

  const sectorData: Record<string, number> = (() => {
    try {
      return snapshot?.sector_data_json
        ? JSON.parse(snapshot.sector_data_json)
        : {}
    } catch { return {} }
  })()

  return {
    snapshot,
    loading,
    refreshing,
    error,
    autoRefreshed,
    refresh,
    sectorData,
    regime: snapshot?.market_regime ?? null,
    isStale: isStale(snapshot),
  }
}
