import { NextRequest, NextResponse } from "next/server"
import { getDb } from "@/lib/db/schema"
import { getCloudflareContext } from "@opennextjs/cloudflare"

// ── /api/market-regime ──────────────────────────────────────────────────────
// Market regime for the breakout-setup gate (see TechnicalRegimeNote + backtest_regime.py).
// Breadth = share of the universe trading above its own 200-day SMA. Uptrend when breadth
// clears the threshold (default 50%). This is the self-contained regime the 10yr backtest
// used to separate "breakout edge years" from the drawdowns where the same setups bled.
//   ?threshold=0.5   uptrend cutoff (0..1)
// Cached 1h in Cloudflare KV (ledger #12 fix: the old "cached" claim was a
// Cache-Control header only — every request paid the 400-day candle scan).
// Keyed per threshold. Regime moves slowly. Research signal, not a buy call.

const CACHE_TTL_S = 3600
async function getKV(): Promise<({ get: (k: string) => Promise<string | null>; put: (k: string, v: string, o?: { expirationTtl?: number }) => Promise<void> }) | null> {
  try { return (getCloudflareContext().env as unknown as { CACHE?: { get: (k: string) => Promise<string | null>; put: (k: string, v: string, o?: { expirationTtl?: number }) => Promise<void> } }).CACHE ?? null; }
  catch { return null; } // not on CF (local/Vercel) → no cache, query direct
}

export async function GET(req: NextRequest) {
  try {
    const sql = getDb()
    const thr = Math.min(0.95, Math.max(0.05, Number(req.nextUrl.searchParams.get("threshold")) || 0.5))

    const kv = await getKV()
    const cacheKey = `market-regime:v1:thr=${thr}`
    if (kv) {
      try {
        const cached = await kv.get(cacheKey)
        if (cached) return new NextResponse(cached, { headers: { "content-type": "application/json", "x-cache": "HIT" } })
      } catch { /* cache read failed — fall through to DB */ }
    }

    // Last ~400 calendar days only → small scan; rank each symbol's candles newest-first,
    // then compare the latest close to the mean of its last 200 closes (a 200-SMA proxy).
    const rows = await sql`
      WITH recent AS (
        SELECT symbol, date, close
        FROM price_candles
        WHERE date >= CURRENT_DATE - INTERVAL '400 days' AND close > 0
      ),
      ranked AS (
        SELECT symbol, close,
               ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
        FROM recent
      ),
      agg AS (
        SELECT symbol,
               AVG(close) FILTER (WHERE rn <= 200) AS sma200,
               MAX(close) FILTER (WHERE rn = 1)    AS last_close,
               COUNT(*)                            AS n
        FROM ranked
        GROUP BY symbol
      )
      SELECT
        COUNT(*) FILTER (WHERE n >= 200 AND last_close > sma200) AS above,
        COUNT(*) FILTER (WHERE n >= 200)                         AS total
      FROM agg
    `

    const asOf = await sql`SELECT MAX(date) AS d FROM price_candles`

    const above = Number(rows?.[0]?.above ?? 0)
    const total = Number(rows?.[0]?.total ?? 0)
    if (!total) {
      return NextResponse.json({ ok: false, error: "no eligible symbols (need >=200 candles)" }, { status: 200 })
    }
    const breadth = above / total
    const regime = breadth >= thr ? "uptrend" : "downtrend"

    const payload = JSON.stringify({
      ok: true,
      regime,                                   // "uptrend" | "downtrend"
      breadth: +breadth.toFixed(4),             // 0..1
      above, total, threshold: thr,
      as_of: asOf?.[0]?.d ?? null,
      note: regime === "uptrend"
        ? "Breakout setups historically add edge in this regime."
        : "Breakout setups historically underperform here — treat with caution.",
    })
    if (kv) {
      try { await kv.put(cacheKey, payload, { expirationTtl: CACHE_TTL_S }) }
      catch { /* cache write failed — response still served */ }
    }
    return new NextResponse(payload, {
      headers: {
        "content-type": "application/json",
        "x-cache": "MISS",
        "Cache-Control": "s-maxage=3600, stale-while-revalidate=86400",
      },
    })
  } catch (err: any) {
    return NextResponse.json({ ok: false, error: err.message }, { status: 500 })
  }
}
