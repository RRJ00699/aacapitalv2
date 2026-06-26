import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

// ── /api/stock/technicals?sym=ABCAPITAL ──────────────────────────────────────
// Computes technicals from price_candles in Neon — the single source of truth —
// NOT from a live broker call or the SimulatedProvider (which is what the old
// app/api/stock/route.ts technicals fall back to). Every block carries its own
// provenance (how many candles, what date span) so the UI can show where the
// numbers came from and never render a silent dead/simulated state.
//
// Reads:  price_candles (daily), price_candles_weekly (weekly),
//         technical_signals (delivery%). Monthly is resampled from daily.
// Research signal, not a buy call.

type Candle = { date: string; open: number; high: number; low: number; close: number; volume: number }

// ── indicator math (ported verbatim from app/api/stock/route.ts) ─────────────
function calcEMA(prices: number[], period: number): number | null {
  if (prices.length < period) return null
  const k = 2 / (period + 1)
  let val = prices.slice(0, period).reduce((a, b) => a + b) / period
  for (let i = period; i < prices.length; i++) val = prices[i] * k + val * (1 - k)
  return +val.toFixed(2)
}

function calcRSI(prices: number[], period = 14): number | null {
  if (prices.length < period + 1) return null
  let gains = 0, losses = 0
  for (let i = prices.length - period; i < prices.length; i++) {
    const diff = prices[i] - prices[i - 1]
    if (diff > 0) gains += diff; else losses -= diff
  }
  const rs = gains / (losses || 0.001)
  return +(100 - 100 / (1 + rs)).toFixed(2)
}

function calcATR(candles: Candle[], period = 14): number | null {
  if (candles.length < period + 1) return null
  const trs = candles.slice(-period - 1).map((c, i, arr) => {
    if (i === 0) return c.high - c.low
    const prev = arr[i - 1]
    return Math.max(c.high - c.low, Math.abs(c.high - prev.close), Math.abs(c.low - prev.close))
  })
  return +(trs.slice(-period).reduce((a, b) => a + b, 0) / period).toFixed(2)
}

function calcPivotPoints(c: Candle) {
  const h = c.high, l = c.low, cl = c.close
  const pivot = +((h + l + cl) / 3).toFixed(2)
  return {
    pivot,
    r1: +(2 * pivot - l).toFixed(2), r2: +(pivot + (h - l)).toFixed(2), r3: +(h + 2 * (pivot - l)).toFixed(2),
    s1: +(2 * pivot - h).toFixed(2), s2: +(pivot - (h - l)).toFixed(2), s3: +(l - 2 * (h - pivot)).toFixed(2),
  }
}

function calcVolumeRatio(candles: Candle[]): number | null {
  if (candles.length < 11) return null
  const last  = candles[candles.length - 1].volume
  const avg10 = candles.slice(-11, -1).reduce((a, c) => a + c.volume, 0) / 10
  return avg10 > 0 ? +(last / avg10).toFixed(2) : null
}

function classifyTrend(ema20: number | null, ema50: number | null, ema200: number | null, price: number): string {
  if (!ema20 || !ema50 || !ema200) return "Unknown"
  if (price > ema20 && ema20 > ema50 && ema50 > ema200) return "Strong Uptrend"
  if (price > ema50 && price > ema200) return "Uptrend"
  if (price < ema20 && ema20 < ema50) return "Downtrend"
  if (price < ema200) return "Below 200 DMA — Bearish"
  return "Sideways"
}

// trading-day % return: last close vs the close `td` sessions ago
function ret(closes: number[], td: number): number | null {
  if (closes.length <= td) return null
  const now = closes[closes.length - 1]
  const then = closes[closes.length - 1 - td]
  if (!then) return null
  return +(((now / then) - 1) * 100).toFixed(2)
}

// Compute a full indicator block for one timeframe's candle series.
// `minBars` guards against fabricating indicators from too little data.
function timeframeBlock(candles: Candle[], minBars = 20) {
  if (candles.length < minBars) {
    return { bars: candles.length, enough: false as const }
  }
  const closes = candles.map(c => c.close)
  const last   = closes[closes.length - 1]
  const ema20  = calcEMA(closes, 20)
  const ema50  = calcEMA(closes, 50)
  const ema200 = calcEMA(closes, 200)
  const rsi    = calcRSI(closes)
  const atr    = calcATR(candles)
  const trend  = classifyTrend(ema20, ema50, ema200, last)
  return {
    bars: candles.length,
    enough: true as const,
    lastClose: +last.toFixed(2),
    ema20, ema50, ema200, rsi, atr, trend,
    atrPct: atr ? +((atr / last) * 100).toFixed(2) : null,
  }
}

// resample daily candles into one candle per calendar month (last close of month)
function resampleMonthly(daily: Candle[]): Candle[] {
  const byMonth = new Map<string, Candle[]>()
  for (const c of daily) {
    const key = c.date.slice(0, 7) // YYYY-MM
    if (!byMonth.has(key)) byMonth.set(key, [])
    byMonth.get(key)!.push(c)
  }
  return [...byMonth.entries()].sort(([a], [b]) => (a < b ? -1 : 1)).map(([, rows]) => ({
    date:   rows[rows.length - 1].date,
    open:   rows[0].open,
    high:   Math.max(...rows.map(r => r.high)),
    low:    Math.min(...rows.map(r => r.low)),
    close:  rows[rows.length - 1].close,
    volume: rows.reduce((a, r) => a + r.volume, 0),
  }))
}

// Normalize a DB date value to 'YYYY-MM-DD' whether Neon returns a JS Date,
// an ISO string, or something else — prevents "Invalid time value" downstream.
function ymd(v: any): string {
  if (v instanceof Date) return Number.isNaN(v.getTime()) ? "" : v.toISOString().slice(0, 10)
  const s = String(v ?? "")
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) return s.slice(0, 10)
  const d = new Date(s)
  return Number.isNaN(d.getTime()) ? "" : d.toISOString().slice(0, 10)
}

const toCandles = (rows: any[], dateKey = "date"): Candle[] =>
  rows.map(r => ({
    date:   ymd(r[dateKey]),
    open:   Number(r.open),
    high:   Number(r.high),
    low:    Number(r.low),
    close:  Number(r.close),
    volume: Number(r.volume) || 0,
  })).filter(c => c.date) // drop any row whose date couldn't be parsed

export async function GET(req: NextRequest) {
  const sym = (req.nextUrl.searchParams.get("sym") || "").trim().toUpperCase()
  if (!sym) return NextResponse.json({ ok: false, error: "sym required" }, { status: 400 })

  try {
    const sql = neon(process.env.DATABASE_URL!)

    // Pull a generous daily window (enough for EMA200 + 1y returns + 52w range).
    const dailyRows = await sql`
      SELECT date, open, high, low, close, volume
      FROM price_candles
      WHERE symbol = ${sym}
      ORDER BY date ASC
    `
    const daily = toCandles(dailyRows as any[])

    // Honest empty state: the sync simply hasn't reached this symbol yet.
    if (daily.length < 20) {
      return NextResponse.json({
        ok: true,
        symbol: sym,
        source: "price_candles",
        technical: null,
        reason: `Only ${daily.length} daily candle(s) in price_candles for ${sym} — the daily sync hasn't covered this symbol yet (or it's newly listed).`,
      })
    }

    const closes  = daily.map(c => c.close)
    const last    = closes[closes.length - 1]
    const lastCdl = daily[daily.length - 1]

    // 52-week range from the last 252 sessions
    const yr   = daily.slice(-252)
    const w52h = +Math.max(...yr.map(c => c.high)).toFixed(2)
    const w52l = +Math.min(...yr.map(c => c.low)).toFixed(2)
    const pctBelowHigh = w52h > 0 ? +(((w52h - last) / w52h) * 100).toFixed(2) : null
    const pctAboveLow  = w52l > 0 ? +(((last - w52l) / w52l) * 100).toFixed(2) : null

    const pivots = calcPivotPoints(lastCdl)

    // Weekly straight from the maintained table; fall back to resample if empty.
    let weeklyCandles: Candle[]
    try {
      const wRows = await sql`
        SELECT week_start AS date, open, high, low, close, volume
        FROM price_candles_weekly
        WHERE symbol = ${sym}
        ORDER BY week_start ASC
      `
      weeklyCandles = toCandles(wRows as any[])
    } catch {
      weeklyCandles = [] // table may not exist in some envs
    }

    // delivery% (latest, if the sync wrote one)
    let deliveryPct: number | null = null
    try {
      const dRows = await sql`
        SELECT delivery_pct FROM technical_signals
        WHERE symbol = ${sym} AND delivery_pct IS NOT NULL
        ORDER BY date DESC LIMIT 1
      `
      const v = (dRows as any[])[0]?.delivery_pct
      deliveryPct = v == null ? null : +Number(v).toFixed(1)
    } catch {
      deliveryPct = null
    }

    const monthly = resampleMonthly(daily)

    return NextResponse.json({
      ok: true,
      symbol: sym,
      source: "price_candles",
      asOf: lastCdl.date,
      coverage: { dailyBars: daily.length, firstDate: daily[0].date, lastDate: lastCdl.date },

      price: {
        last: +last.toFixed(2),
        week52High: w52h,
        week52Low:  w52l,
        pctBelow52WHigh: pctBelowHigh,
        pctAbove52WLow:  pctAboveLow,
      },

      returns: {
        r1m: ret(closes, 21),
        r3m: ret(closes, 63),
        r6m: ret(closes, 126),
        r1y: ret(closes, 252),
      },

      // indicators per timeframe — each says how many bars it used; thin ones return enough:false
      daily:   timeframeBlock(daily, 20),
      weekly:  weeklyCandles.length >= 20 ? timeframeBlock(weeklyCandles, 20) : timeframeBlock(resampleWeekly(daily), 20),
      monthly: timeframeBlock(monthly, 6),

      structure: {
        pivots,
        volumeRatio: calcVolumeRatio(daily),
        deliveryPct,
      },

      note: "research signal, not a buy call",
    })
  } catch (e: any) {
    return NextResponse.json({ ok: false, error: String(e?.message || e) }, { status: 500 })
  }
}

// fallback weekly resample (W-MON, close of week) when price_candles_weekly is empty
function resampleWeekly(daily: Candle[]): Candle[] {
  const byWeek = new Map<string, Candle[]>()
  for (const c of daily) {
    const d = new Date(c.date + "T00:00:00Z")
    if (Number.isNaN(d.getTime())) continue        // skip unparseable, never throw
    const day = d.getUTCDay() || 7        // Mon=1..Sun=7
    const monday = new Date(d); monday.setUTCDate(d.getUTCDate() - (day - 1))
    const key = monday.toISOString().slice(0, 10)
    if (!byWeek.has(key)) byWeek.set(key, [])
    byWeek.get(key)!.push(c)
  }
  return [...byWeek.entries()].sort(([a], [b]) => (a < b ? -1 : 1)).map(([, rows]) => ({
    date:   rows[0].date,
    open:   rows[0].open,
    high:   Math.max(...rows.map(r => r.high)),
    low:    Math.min(...rows.map(r => r.low)),
    close:  rows[rows.length - 1].close,
    volume: rows.reduce((a, r) => a + r.volume, 0),
  }))
}
