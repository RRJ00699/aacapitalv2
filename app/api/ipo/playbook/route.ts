// app/api/ipo/playbook/route.ts
// Returns IPO playbook data — all IPOs with play recommendations
// CHANGE (additive): mainboard only (is_sme=false), drop malformed-size rows,
// and dedupe BSE/name twins so each IPO appears once (the clean NSE row wins).

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
      WITH deduped AS (
        SELECT *,
          ROW_NUMBER() OVER (
            -- one row per company, ignoring Ltd/Limited/Pvt and punctuation/case
            PARTITION BY regexp_replace(
                           regexp_replace(lower(company_name), '(limited|ltd|lim|private|pvt)', '', 'g'),
                           '[^a-z0-9]', '', 'g')
            ORDER BY
              -- prefer the row with a real NSE symbol …
              (CASE WHEN symbol IS NOT NULL AND symbol <> '' THEN 0 ELSE 1 END),
              -- … a sane issue size (BSE twin had ₹32,901,878 cr garbage) …
              (CASE WHEN issue_size_cr IS NOT NULL AND issue_size_cr > 0 AND issue_size_cr < 100000 THEN 0 ELSE 1 END),
              -- … and a populated play recommendation
              (CASE WHEN play_recommendation IS NOT NULL AND play_recommendation <> '' THEN 0 ELSE 1 END),
              updated_at DESC NULLS LAST
          ) AS _rn
        FROM ipo_intelligence
        WHERE COALESCE(is_sme, false) = false                       -- mainboard only
          AND (issue_size_cr IS NULL OR issue_size_cr < 100000)     -- drop malformed-size junk rows
      )
      SELECT base.*,
        iid.roce_pct, iid.debt_equity, iid.pe_post AS iid_pe_post,
        iid.promoter_post_pct, iid.pat_margin_pct,
        iid.issue_amount_cr AS iid_issue_cr, iid.industry AS iid_industry,
        iid.registrar AS iid_registrar
      FROM (
      SELECT
        id, company_name, symbol, sector, is_sme,
        issue_price, issue_size_cr, fresh_issue_ratio, ofs_pct,
        listing_date, open_date, close_date,
        gmp_pct_t10, gmp_pct_t7, gmp_pct_t5, gmp_pct_t3, gmp_pct_t1,
        gmp_momentum, gmp_max_pct, gmp_min_pct, gmp_day_before_pct, gmp_history,
        qib_subscription_x, nii_subscription_x, rii_subscription_x, total_subscription_x,
        sub_day1_qib, sub_day2_qib, sub_day3_qib, qib_backloaded,
        anchor_quality, anchor_tier1_count, anchor_count, anchor_names,
        anchor_stalwart_names, anchor_investors,
        anchor_lock30_date, anchor_lock90_date,
        listing_open, listing_day_high, listing_day_low, listing_day_close,
        listing_day_vwap, listing_vs_gmp_pct,
        hit_uc_day1, hit_lc_day1, hit_uc_day2, hit_lc_day2,
        brlm_names, brlm_score, brlm_avg_listing_gain, brlm_pct_negative, brlm_tier,
        lqi_final, archetype,
        operator_risk_score, operator_risk_flags,
        buy_at_open_score, vwap_entry_score,
        return_listing_open, return_day1_close,
        return_day7, return_day30, return_day90, return_day180, return_day365,
        max_upside_pct,
        play_recommendation, play_confidence, play_reasons,
        play_stop_loss_pct, play_target_pct, play_hold_window,
        similar_ipos, suggested_action,
        prob_10pct_profit, prob_loss_gt10, expected_return,
        ipo_pe, peer_median_pe, valuation_premium_pct,
        india_vix, listing_regime,
        lot_size,
        updated_at
      FROM deduped
      WHERE _rn = 1
        AND (${play} = '' OR play_recommendation = ${play}
             OR suggested_action ILIKE ${'%' + play + '%'})
        AND (${search} = '' OR company_name ILIKE ${'%' + search + '%'})
      ) base
      LEFT JOIN ipo_issue_details iid ON iid.nse_symbol = base.symbol
      ORDER BY
        CASE
          WHEN base.listing_date IS NULL THEN 0
          WHEN base.listing_date >= CURRENT_DATE THEN 1
          WHEN base.listing_date >= CURRENT_DATE - INTERVAL '30 days' THEN 2
          ELSE 3
        END ASC,
        CASE WHEN base.play_recommendation = 'BUY_AT_OPEN'    THEN 1
             WHEN base.play_recommendation = 'BUY_PANIC_DIP'  THEN 2
             WHEN base.play_recommendation = 'WAIT_FOR_VWAP'  THEN 3
             WHEN base.play_recommendation = 'BUY_AFTER_DAY3' THEN 4
             WHEN base.play_recommendation = 'AVOID'          THEN 6
             ELSE 5
        END ASC,
        base.listing_date DESC NULLS LAST
      LIMIT ${limit}
    `

    return NextResponse.json({ ok: true, ipos: rows, total: rows.length })

  } catch (err: any) {
    return NextResponse.json({ ok: false, error: err.message }, { status: 500 })
  }
}
