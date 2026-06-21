// app/api/ipo/playbook/route.ts
// Returns IPO playbook data — all IPOs with play recommendations
// Computes play scores from existing ipo_intelligence data

import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

export const dynamic = "force-dynamic"

export async function GET(req: NextRequest) {
  const sql = neon(process.env.DATABASE_URL!)
  const { searchParams } = new URL(req.url)
  const limit  = Math.min(100, parseInt(searchParams.get("limit") || "50"))
  const play   = searchParams.get("play") || ""
  const search = searchParams.get("search") || ""

  try {
    const rows = await sql`
      SELECT
        id, company_name, symbol, sector, is_sme,
        issue_price, issue_size_cr, fresh_issue_ratio, ofs_pct,
        listing_date, open_date, close_date,

        -- GMP
        gmp_pct_t10, gmp_pct_t7, gmp_pct_t5, gmp_pct_t3, gmp_pct_t1,
        gmp_momentum, gmp_max_pct, gmp_min_pct, gmp_day_before_pct, gmp_history,

        -- Subscription
        qib_subscription_x, nii_subscription_x, rii_subscription_x, total_subscription_x,
        sub_day1_qib, sub_day2_qib, sub_day3_qib, qib_backloaded,

        -- Anchors
        anchor_quality, anchor_tier1_count, anchor_count, anchor_names,
        anchor_stalwart_names, anchor_investors,
        anchor_lock30_date, anchor_lock90_date,

        -- Listing day
        listing_open, listing_day_high, listing_day_low, listing_day_close,
        listing_day_vwap, listing_vs_gmp_pct,
        hit_uc_day1, hit_lc_day1, hit_uc_day2, hit_lc_day2,

        -- BRLM
        brlm_names, brlm_score, brlm_avg_listing_gain, brlm_pct_negative, brlm_tier,

        -- Scores
        lqi_final, archetype,
        operator_risk_score, operator_risk_flags,
        buy_at_open_score, vwap_entry_score,

        -- Returns
        return_listing_open, return_day1_close,
        return_day7, return_day30, return_day90, return_day180, return_day365,
        max_upside_pct,

        -- Play
        play_recommendation, play_confidence, play_reasons,
        play_stop_loss_pct, play_target_pct, play_hold_window,

        -- Extras
        similar_ipos, suggested_action,
        prob_10pct_profit, prob_loss_gt10, expected_return,
        ipo_pe, peer_median_pe, valuation_premium_pct,
        india_vix, listing_regime,
        lot_size,
        updated_at

      FROM ipo_intelligence
      WHERE (${play} = '' OR play_recommendation = ${play}
             OR suggested_action ILIKE ${'%' + play + '%'})
        AND (${search} = '' OR company_name ILIKE ${'%' + search + '%'})
      ORDER BY
        -- Upcoming and recent first
        CASE
          WHEN listing_date IS NULL THEN 0
          WHEN listing_date >= CURRENT_DATE THEN 1
          WHEN listing_date >= CURRENT_DATE - INTERVAL '30 days' THEN 2
          ELSE 3
        END ASC,
        -- Then by play quality within each group
        CASE WHEN play_recommendation = 'BUY_AT_OPEN'    THEN 1
             WHEN play_recommendation = 'BUY_PANIC_DIP'  THEN 2
             WHEN play_recommendation = 'WAIT_FOR_VWAP'  THEN 3
             WHEN play_recommendation = 'BUY_AFTER_DAY3' THEN 4
             WHEN play_recommendation = 'AVOID'          THEN 6
             ELSE 5
        END ASC,
        listing_date DESC NULLS LAST
    `.catch(() => [])

    return NextResponse.json({ ok: true, ipos: rows, total: rows.length })

  } catch (err: any) {
    return NextResponse.json({ ok: false, error: err.message }, { status: 500 })
  }
}
