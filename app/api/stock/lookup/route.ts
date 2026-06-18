import { NextRequest, NextResponse } from 'next/server'
import { sql, localSql, normalizeSymbol } from '@/lib/db'

export const dynamic = 'force-dynamic'
const num = (v: any, f = 0) => { const x = Number(v); return Number.isFinite(x) ? x : f }

function ema(values: number[], period: number) {
  if (values.length < period) return null
  const k = 2 / (period + 1)
  let e = values.slice(0, period).reduce((a, b) => a + b, 0) / period
  for (let i = period; i < values.length; i++) e = values[i] * k + e * (1 - k)
  return Number(e.toFixed(2))
}
function rsi(values: number[], period = 14) {
  if (values.length < period + 1) return null
  let g = 0, l = 0
  for (let i = values.length - period; i < values.length; i++) {
    const d = values[i] - values[i - 1]
    if (d >= 0) g += d; else l -= d
  }
  const rs = g / (l || 0.0001)
  return Number((100 - 100 / (1 + rs)).toFixed(2))
}
function atr(c: any[], period = 14) {
  if (c.length < period + 1) return 0
  const trs = c.slice(-period - 1).map((x, i, a) => i === 0 ? num(x.high) - num(x.low) : Math.max(num(x.high) - num(x.low), Math.abs(num(x.high) - num(a[i-1].close)), Math.abs(num(x.low) - num(a[i-1].close))))
  return trs.slice(-period).reduce((a, b) => a + b, 0) / period
}

export async function GET(req: NextRequest) {
  const symbol = normalizeSymbol(req.nextUrl.searchParams.get('symbol'))
  if (!symbol) return NextResponse.json({ ok: false, error: 'symbol required' }, { status: 400 })

  const profileRows = await sql`
    SELECT cm.symbol, cm.company_name, cm.sector, cm.market_cap_cr,
           q.revenue_growth_pct, q.net_profit_growth_pct, q.opm_pct,
           e.score AS earnings_score, t.buy_zone_score, t.signal
    FROM company_master cm
    LEFT JOIN LATERAL (
      SELECT revenue_growth_pct, net_profit_growth_pct, opm_pct FROM quarterly_results qr
      WHERE qr.symbol = cm.symbol ORDER BY COALESCE(qr.period_end, qr.quarter_end, NOW()) DESC LIMIT 1
    ) q ON TRUE
    LEFT JOIN LATERAL (
      SELECT score FROM earnings_acceleration_scores eas WHERE eas.symbol = cm.symbol ORDER BY COALESCE(eas.period_end, eas.created_at, NOW()) DESC LIMIT 1
    ) e ON TRUE
    LEFT JOIN technical_signals t ON t.symbol = cm.symbol
    WHERE cm.symbol = ${symbol}
    LIMIT 1
  `.catch(() => [])

  const candles = await localSql`
    SELECT trade_date, open, high, low, close, volume
    FROM price_candles
    WHERE symbol = ${symbol}
    ORDER BY trade_date DESC
    LIMIT 260
  `.catch(() => [])

  const ordered = candles.slice().reverse()
  const closes = ordered.map((c: any) => num(c.close)).filter(Boolean)
  const last = ordered[ordered.length - 1]
  const price = num(last?.close)
  const a = atr(ordered)
  const levels = last ? {
    support: [price - a, price - 2 * a, price - 3 * a].map(x => Number(x.toFixed(2))),
    resistance: [price + a, price + 2 * a, price + 3 * a].map(x => Number(x.toFixed(2))),
    targets: [price + 1.5 * a, price + 2.5 * a, price + 4 * a].map(x => Number(x.toFixed(2))),
    stopLoss: Number((price - 1.6 * a).toFixed(2)),
  } : { support: [], resistance: [], targets: [], stopLoss: 0 }

  const p = profileRows[0] as any || { symbol }
  return NextResponse.json({
    ok: true,
    stock: {
      symbol,
      name: p.company_name || symbol,
      sector: p.sector || null,
      market_cap_cr: num(p.market_cap_cr),
      price,
      rsi: rsi(closes),
      ema20: ema(closes, 20),
      ema50: ema(closes, 50),
      ema200: ema(closes, 200),
      volume: num(last?.volume),
      revenue_growth_pct: num(p.revenue_growth_pct),
      profit_growth_pct: num(p.net_profit_growth_pct),
      opm_pct: num(p.opm_pct),
      earnings_score: num(p.earnings_score),
      technical_score: num(p.buy_zone_score),
      signal: p.signal || null,
      ...levels,
      chart: ordered.slice(-90),
      source: candles.length ? 'local_postgres_price_candles' : 'profile_only_neon',
    }
  })
}
