import { NextRequest, NextResponse } from "next/server"
import { getDb } from "@/lib/db/schema"

// ── /api/deals ───────────────────────────────────────────────────────────────
// Surfaces institutional_large_deals (NSE bulk/block deals) to the UI — the table
// the daily fetch + historical importer populate but nothing read before.
//   ?symbol=RELIANCE   → recent deals for one stock + net buy/sell summary (workboard)
//   (no symbol)        → recent deals across the market + net-flow movers (universe)
// Window: ?days=30 (default), rows: ?limit=50 (default). Research signal, not a buy call.

const num = (v: any): number | null => {
  if (v === null || v === undefined) return null
  const n = Number(v); return Number.isFinite(n) ? n : null
}

export async function GET(req: NextRequest) {
  try {
    const sql = getDb()
    const p = req.nextUrl.searchParams
    const symbol = (p.get("symbol") || "").trim().toUpperCase()
    // symbol mode = per-stock history (default ~10yr); universe mode = recent 30d movers
    const daysParam = p.get("days")
    const defDays = symbol ? 3650 : 30
    const days = Math.min(3650, Math.max(1, Number(daysParam || defDays) || defDays))
    const limit = Math.min(200, Math.max(1, Number(p.get("limit") || (symbol ? 100 : 50)) || (symbol ? 100 : 50)))

    if (symbol) {
      const rows = await sql`
        SELECT deal_date, client_name, deal_type, transaction_type, quantity, trade_price
        FROM institutional_large_deals
        WHERE ticker = ${symbol} AND deal_date >= CURRENT_DATE - ${days}::int
        ORDER BY deal_date DESC, quantity DESC
        LIMIT ${limit}`
      const deals = (rows as any[]).map(r => {
        const qty = num(r.quantity) ?? 0, price = num(r.trade_price) ?? 0
        const value = qty * price
        return {
          date: String(r.deal_date).slice(0, 10),
          client: r.client_name, deal_type: r.deal_type, side: r.transaction_type,
          quantity: qty, price, value: +value.toFixed(0),
        }
      })
      // Bulk deals carry a real direction (single-side disclosure). Block deals report
      // BOTH counterparties, so buy≈sell and net is always ~0 — show their turnover instead.
      let bulkBuy = 0, bulkSell = 0, bulkN = 0, blockTurnover = 0, blockN = 0
      for (const d of deals) {
        if (d.deal_type === "BLOCK") { blockTurnover += d.value; blockN++ }
        else {
          if (d.side === "BUY") bulkBuy += d.value
          else if (d.side === "SELL") bulkSell += d.value
          bulkN++
        }
      }
      return NextResponse.json({
        ok: true, symbol, window_days: days, count: deals.length,
        summary: {
          bulk_buy: +bulkBuy.toFixed(0), bulk_sell: +bulkSell.toFixed(0),
          bulk_net: +(bulkBuy - bulkSell).toFixed(0), bulk_count: bulkN,
          block_turnover: +blockTurnover.toFixed(0), block_count: blockN,
        },
        deals,
        disclaimer: "Bulk deals show net direction; block deals report both sides (net ≈ 0), shown as turnover. Research signal, not a buy call.",
      })
    }

    // universe mode — recent deals + net-flow movers over the window
    const [recentRows, flowRows] = await Promise.all([
      sql`SELECT deal_date, ticker, client_name, deal_type, transaction_type, quantity, trade_price
          FROM institutional_large_deals
          WHERE deal_date >= CURRENT_DATE - ${days}::int
          ORDER BY deal_date DESC, quantity DESC
          LIMIT ${limit}`,
      sql`SELECT ticker,
                 SUM(CASE WHEN transaction_type='BUY'  THEN quantity*trade_price ELSE 0 END) AS buy_value,
                 SUM(CASE WHEN transaction_type='SELL' THEN quantity*trade_price ELSE 0 END) AS sell_value,
                 COUNT(*) AS deals
          FROM institutional_large_deals
          WHERE deal_date >= CURRENT_DATE - ${days}::int
          GROUP BY ticker
          HAVING COUNT(*) > 0`,
    ])

    const flows = (flowRows as any[]).map(r => {
      const bv = num(r.buy_value) ?? 0, sv = num(r.sell_value) ?? 0
      return { ticker: r.ticker, buy_value: +bv.toFixed(0), sell_value: +sv.toFixed(0),
               net_value: +(bv - sv).toFixed(0), deals: Number(r.deals) }
    })
    const byNet = [...flows].sort((a, b) => b.net_value - a.net_value)

    const recent = (recentRows as any[]).map(r => {
      const qty = num(r.quantity) ?? 0, price = num(r.trade_price) ?? 0
      return {
        date: String(r.deal_date).slice(0, 10), ticker: r.ticker, client: r.client_name,
        deal_type: r.deal_type, side: r.transaction_type, quantity: qty, price,
        value: +(qty * price).toFixed(0),
      }
    })

    return NextResponse.json({
      ok: true, window_days: days, count: recent.length,
      recent,
      top_buys: byNet.slice(0, 15),
      top_sells: byNet.slice(-15).reverse(),
      disclaimer: "Net flow = Σ(buy value − sell value) over the window. Research signal, not a buy call.",
    })
  } catch (e: any) {
    return NextResponse.json({ ok: false, error: String(e?.message || e) }, { status: 500 })
  }
}
