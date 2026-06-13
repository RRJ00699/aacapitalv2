import { NextResponse } from "next/server"
import { sql } from "@/lib/db"

export const dynamic = "force-dynamic"

export async function GET() {
  try {
    const [snapshot, regime, flows] = await Promise.all([
      sql`SELECT market_regime,nifty_price,banknifty_price,vix,fii_flow,dii_flow,pcr,breadth_pct,last_updated FROM market_snapshot WHERE id=1 LIMIT 1`.catch(()=>[]),
      sql`SELECT active_regime,nifty_close,nifty_ema_200,breadth_percentage,recommended_allocation_min,recommended_allocation_max,evaluation_date FROM market_regimes ORDER BY evaluation_date DESC LIMIT 1`.catch(()=>[]),
      sql`SELECT fii_net,dii_net,trade_date FROM daily_institutional_flows ORDER BY trade_date DESC LIMIT 1`.catch(()=>[]),
    ])

    const snap = snapshot[0] as any || {}
    const reg  = regime[0]   as any || {}
    const flow = flows[0]    as any || {}

    return NextResponse.json({
      ok: true,
      data: {
        regime:      reg.active_regime || snap.market_regime || "NORMAL",
        nifty_price: snap.nifty_price  || reg.nifty_close,
        nifty_ema200:reg.nifty_ema_200,
        breadth_pct: reg.breadth_percentage || snap.breadth_pct,
        deploy_min:  reg.recommended_allocation_min  ?? 50,
        deploy_max:  reg.recommended_allocation_max  ?? 70,
        vix:         snap.vix,
        fii_flow:    flow.fii_net || snap.fii_flow,
        dii_flow:    flow.dii_net || snap.dii_flow,
        last_updated:snap.last_updated || reg.evaluation_date,
      }
    })
  } catch (error: unknown) {
    // Never crash the Today screen — return safe default
    return NextResponse.json({
      ok: true,
      data: { regime:"NORMAL", deploy_min:50, deploy_max:70 },
      error: String(error),
    })
  }
}
