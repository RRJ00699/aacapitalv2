// _scripts/run-intelligence-scoring.ts
// Scores all earnings, commentary, and AMFI data in Neon DB
// Usage:
//   npx tsx _scripts/run-intelligence-scoring.ts                    (all)
//   npx tsx _scripts/run-intelligence-scoring.ts --module=earnings
//   npx tsx _scripts/run-intelligence-scoring.ts --module=commentary
//   npx tsx _scripts/run-intelligence-scoring.ts --module=amfi

import { Pool } from 'pg'
import { config } from 'dotenv'
import { existsSync } from 'fs'
import path from 'path'
import { scoreEarnings } from '../lib/intelligence/earnings-score'
import { scoreManagementCommentary } from '../lib/intelligence/commentary-score'
import { scoreAmfiLiquidity } from '../lib/intelligence/amfi-score'

const envPath = path.resolve(process.cwd(), '.env.local')
if (existsSync(envPath)) config({ path: envPath })
else config()

const MODULE = process.argv.find(a => a.startsWith('--module='))?.split('=')[1] || 'all'

async function getPool() {
  const connStr = process.env.DATABASE_URL || process.env.NEON_DATABASE_URL
  if (!connStr) throw new Error('DATABASE_URL not set')
  return new Pool({ connectionString: connStr, ssl: { rejectUnauthorized: false } })
}

async function scoreAllEarnings(pool: Pool) {
  const { rows } = await pool.query('SELECT * FROM quarterly_results')
  let count = 0
  for (const row of rows) {
    const score = scoreEarnings(row as any)
    await pool.query(`
      INSERT INTO earnings_acceleration_scores (
        symbol, company_name, fiscal_year, fiscal_quarter,
        revenue_acceleration_score, pat_acceleration_score, margin_expansion_score,
        consistency_score, total_score, acceleration_status, score_details, updated_at
      ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::jsonb,now())
      ON CONFLICT (symbol, fiscal_year, fiscal_quarter) DO UPDATE SET
        revenue_acceleration_score = EXCLUDED.revenue_acceleration_score,
        pat_acceleration_score = EXCLUDED.pat_acceleration_score,
        margin_expansion_score = EXCLUDED.margin_expansion_score,
        consistency_score = EXCLUDED.consistency_score,
        total_score = EXCLUDED.total_score,
        acceleration_status = EXCLUDED.acceleration_status,
        score_details = EXCLUDED.score_details,
        updated_at = now()
    `, [
      score.symbol, score.company_name, score.fiscal_year, score.fiscal_quarter,
      score.revenue_acceleration_score, score.pat_acceleration_score,
      score.margin_expansion_score, score.consistency_score,
      score.total_score, score.acceleration_status,
      JSON.stringify(score.score_details)
    ])
    count++
  }
  return count
}

async function scoreAllCommentary(pool: Pool) {
  const { rows } = await pool.query('SELECT * FROM management_commentary_normalized')
  let count = 0
  for (const row of rows) {
    const score = scoreManagementCommentary(row as any)
    await pool.query(`
      INSERT INTO management_commentary_scores (
        symbol, company_name, fiscal_quarter, demand_score, margin_score,
        order_book_score, guidance_score, risk_score, confidence_score,
        total_score, commentary_status, score_reason, score_details, updated_at
      ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13::jsonb,now())
      ON CONFLICT (symbol, fiscal_year, fiscal_quarter) DO UPDATE SET
        demand_score = EXCLUDED.demand_score,
        margin_score = EXCLUDED.margin_score,
        order_book_score = EXCLUDED.order_book_score,
        guidance_score = EXCLUDED.guidance_score,
        risk_score = EXCLUDED.risk_score,
        confidence_score = EXCLUDED.confidence_score,
        total_score = EXCLUDED.total_score,
        commentary_status = EXCLUDED.commentary_status,
        score_reason = EXCLUDED.score_reason,
        score_details = EXCLUDED.score_details,
        updated_at = now()
    `, [
      score.symbol, score.company_name, score.fiscal_quarter,
      score.demand_score, score.margin_score, score.order_book_score,
      score.guidance_score, score.risk_score, score.confidence_score,
      score.total_score, score.commentary_status, score.score_reason,
      JSON.stringify(score.score_details)
    ])
    count++
  }
  return count
}

async function scoreAllAmfi(pool: Pool) {
  const { rows: periods } = await pool.query(
    'SELECT DISTINCT report_year, report_month FROM amfi_category_flows ORDER BY report_year DESC, report_month DESC'
  )
  let count = 0
  for (const period of periods) {
    const { rows: flows } = await pool.query(
      'SELECT * FROM amfi_category_flows WHERE report_year=$1 AND report_month=$2',
      [period.report_year, period.report_month]
    )
    if (flows.length === 0) continue
    const score = scoreAmfiLiquidity(flows as any)
    await pool.query(`
      INSERT INTO amfi_commentary_scores (
        report_month, report_year, equity_flow_score, sip_strength_score,
        smallcap_heat_score, midcap_heat_score, debt_shift_score, liquidity_score,
        total_score, liquidity_status, score_reason, score_details, updated_at
      ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb,now())
      ON CONFLICT (report_month, report_year) DO UPDATE SET
        equity_flow_score = EXCLUDED.equity_flow_score,
        sip_strength_score = EXCLUDED.sip_strength_score,
        smallcap_heat_score = EXCLUDED.smallcap_heat_score,
        midcap_heat_score = EXCLUDED.midcap_heat_score,
        debt_shift_score = EXCLUDED.debt_shift_score,
        liquidity_score = EXCLUDED.liquidity_score,
        total_score = EXCLUDED.total_score,
        liquidity_status = EXCLUDED.liquidity_status,
        score_reason = EXCLUDED.score_reason,
        score_details = EXCLUDED.score_details,
        updated_at = now()
    `, [
      score.report_month, score.report_year, score.equity_flow_score,
      score.sip_strength_score, score.smallcap_heat_score, score.midcap_heat_score,
      score.debt_shift_score, score.liquidity_score, score.total_score,
      score.liquidity_status, score.score_reason, JSON.stringify(score.score_details)
    ])
    count++
  }
  return count
}

async function main() {
  console.log(`\nAACapital Intelligence Scoring — module: ${MODULE}`)
  const pool = await getPool()
  try {
    if (MODULE === 'all' || MODULE === 'earnings') {
      const n = await scoreAllEarnings(pool)
      console.log(`✓ Earnings scored: ${n} records`)
    }
    if (MODULE === 'all' || MODULE === 'commentary') {
      const n = await scoreAllCommentary(pool)
      console.log(`✓ Commentary scored: ${n} records`)
    }
    if (MODULE === 'all' || MODULE === 'amfi') {
      const n = await scoreAllAmfi(pool)
      console.log(`✓ AMFI scored: ${n} periods`)
    }
    console.log('\n✅ Scoring complete')
  } finally {
    await pool.end()
  }
}

main().catch(e => { console.error(e); process.exit(1) })
