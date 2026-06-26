import { NextRequest, NextResponse } from "next/server"
import { getDb } from "@/lib/db/schema"

// ── /api/convergence/changes ─────────────────────────────────────────────────
// "What changed since last look." Diffs the latest convergence_history snapshot
// against a reference date and returns, per symbol, the delta on the composite
// convergence score + all five factors + any action change, with a generated
// one-line headline. The shared backbone for the Watch screen (#2) and the
// verdict-header "what changed" strip (#3).
//
// convergence_history is point-in-time (snapshot_convergence.py appends one dated
// row per stock per daily run), so these deltas are honest — not today's scores
// projected backwards. Research signal, not a buy call.
//
// Scope (pick one):
//   ?symbol=RELIANCE      single stock            → verdict-header strip (#3)
//   ?watchlist=1          only watchlist_stocks   → Watch screen (#2)
//   ?symbols=A,B,C        explicit list
//   (none)               whole universe, movers first
// Window / filter:
//   ?since=YYYY-MM-DD     reference "last look" date (default: previous snapshot)
//   ?min=5               minimum |convergence delta| to include (default 0)
//   ?limit=100           cap rows (default 100, max 500)

const num = (v: any): number | null => {
  if (v === null || v === undefined) return null
  const n = Number(v); return Number.isFinite(n) ? n : null
}

const FACTORS = ["business", "earnings", "technical", "smart_money", "sector"] as const
const LABEL: Record<string, string> = {
  business: "Business", earnings: "Earnings", technical: "Technical",
  smart_money: "Smart money", sector: "Sector",
}

type Row = {
  nse_symbol: string
  convergence: any; business: any; earnings: any; technical: any
  smart_money: any; sector: any; action: string | null
}

const delta = (now: number | null, prev: number | null): number | null =>
  now === null || prev === null ? null : Math.round(now - prev)

function statusOf(d: number | null, inNow: boolean, inPrev: boolean): string {
  if (inNow && !inPrev) return "new"
  if (!inNow && inPrev) return "dropped"
  if (d === null) return "flat"
  if (d >= 2) return "up"
  if (d <= -2) return "down"
  return "flat"
}

function headline(c: any): string {
  if (c.status === "new")     return `New to the ranking at ${c.convergence.now ?? "—"}`
  if (c.status === "dropped") return `Dropped from the ranking (was ${c.convergence.prev ?? "—"})`
  const bits: string[] = []
  const cd = c.convergence.delta
  if (cd !== null && cd !== 0) bits.push(`Convergence ${cd > 0 ? "+" : ""}${cd} (${c.convergence.prev}→${c.convergence.now})`)
  // biggest single-factor move
  let best: { name: string; d: number } | null = null
  for (const f of FACTORS) {
    const d = c.factors[f].delta
    if (d !== null && d !== 0 && (best === null || Math.abs(d) > Math.abs(best.d))) best = { name: f, d }
  }
  if (best) bits.push(`${LABEL[best.name]} ${best.d > 0 ? "+" : ""}${best.d}`)
  if (c.action_changed) bits.push(`${c.action_prev ?? "—"} → ${c.action ?? "—"}`)
  return bits.length ? bits.join(" · ") : "No material change since last snapshot"
}

export async function GET(req: NextRequest) {
  try {
    const sql = getDb()
    const p = req.nextUrl.searchParams
    const symbol       = (p.get("symbol") || "").trim().toUpperCase()
    const symbolsParam = (p.get("symbols") || "").trim()
    const useWatchlist = p.get("watchlist") === "1" || p.get("watchlist") === "true"
    const since        = (p.get("since") || "").trim() // YYYY-MM-DD
    const minDelta     = Math.max(0, Number(p.get("min") || 0) || 0)
    const limit        = Math.min(500, Math.max(1, Number(p.get("limit") || 100) || 100))

    // latest snapshot date (::text so we compare/echo plain YYYY-MM-DD, never a JS Date)
    const latestQ = await sql`SELECT MAX(run_date)::text AS d FROM convergence_history`
    const latest = (latestQ as any[])[0]?.d as string | null
    if (!latest) {
      return NextResponse.json({
        ok: true, compared: false, latest_date: null, since_date: null, count: 0, changes: [],
        reason: "convergence_history is empty — the daily snapshot hasn't run yet.",
      })
    }

    // reference ("last look") date: latest run strictly before `latest`, or on/before `since`
    const prevQ = since
      ? await sql`SELECT MAX(run_date)::text AS d FROM convergence_history WHERE run_date <= ${since} AND run_date < ${latest}`
      : await sql`SELECT MAX(run_date)::text AS d FROM convergence_history WHERE run_date < ${latest}`
    const prevDate = (prevQ as any[])[0]?.d as string | null

    // resolve symbol scope
    let scope: string[] | null = null
    if (symbol) {
      scope = [symbol]
    } else if (symbolsParam) {
      scope = symbolsParam.split(",").map(s => s.trim().toUpperCase()).filter(Boolean)
    } else if (useWatchlist) {
      const w = await sql`SELECT symbol FROM watchlist_stocks`
      scope = (w as any[]).map(r => String(r.symbol).toUpperCase())
      if (!scope.length) {
        return NextResponse.json({
          ok: true, compared: !!prevDate, latest_date: latest, since_date: prevDate,
          count: 0, changes: [], reason: "Watchlist is empty.",
        })
      }
    }

    const fetchSlice = async (d: string): Promise<Row[]> => {
      const rows = scope
        ? await sql`SELECT nse_symbol, convergence, business, earnings, technical, smart_money, sector, action
                    FROM convergence_history WHERE run_date = ${d} AND nse_symbol = ANY(${scope})`
        : await sql`SELECT nse_symbol, convergence, business, earnings, technical, smart_money, sector, action
                    FROM convergence_history WHERE run_date = ${d}`
      return rows as any as Row[]
    }

    const nowRows  = await fetchSlice(latest)
    const prevRows = prevDate ? await fetchSlice(prevDate) : []

    const nowMap  = new Map<string, Row>()
    const prevMap = new Map<string, Row>()
    for (const r of nowRows)  nowMap.set(String(r.nse_symbol).toUpperCase(), r)
    for (const r of prevRows) prevMap.set(String(r.nse_symbol).toUpperCase(), r)

    const syms = new Set<string>([...nowMap.keys(), ...prevMap.keys()])

    const changes = [...syms].map(s => {
      const a = nowMap.get(s), b = prevMap.get(s)
      const cNow = num(a?.convergence ?? null), cPrev = num(b?.convergence ?? null)
      const cDelta = delta(cNow, cPrev)

      const factors: Record<string, { now: number | null; prev: number | null; delta: number | null }> = {}
      for (const f of FACTORS) {
        const fn = num((a as any)?.[f] ?? null), fp = num((b as any)?.[f] ?? null)
        factors[f] = { now: fn, prev: fp, delta: delta(fn, fp) }
      }

      const actionNow = a?.action ?? null, actionPrev = b?.action ?? null
      const status = statusOf(cDelta, !!a, !!b)
      const c: any = {
        symbol: s,
        convergence: { now: cNow, prev: cPrev, delta: cDelta },
        factors,
        action: actionNow,
        action_prev: actionPrev,
        action_changed: !!a && !!b && actionNow !== actionPrev,
        status,
      }
      c.headline = headline(c)
      // sort weight: new/dropped float to the top, then biggest absolute convergence move
      c.abs_move = (status === "new" || status === "dropped") ? 1000
                 : cDelta === null ? -1 : Math.abs(cDelta)
      return c
    })

    let out = changes
    if (minDelta > 0) {
      out = out.filter(c =>
        c.status === "new" || c.status === "dropped" ||
        (c.convergence.delta !== null && Math.abs(c.convergence.delta) >= minDelta))
    }
    out.sort((x, y) => y.abs_move - x.abs_move)
    out = out.slice(0, limit)

    return NextResponse.json({
      ok: true,
      compared: !!prevDate,
      latest_date: latest,
      since_date: prevDate,
      count: out.length,
      changes: out,
      disclaimer: "Point-in-time convergence deltas. Research signal, not a buy call.",
    })
  } catch (e: any) {
    return NextResponse.json({ ok: false, error: String(e?.message || e) }, { status: 500 })
  }
}
