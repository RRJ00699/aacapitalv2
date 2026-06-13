// _scripts/seed-intelligence-sample.ts
// Seeds sample data for WABAG, KAYNES, NETWEB, MTARTECH
// Safe to re-run — uses ON CONFLICT DO UPDATE
// Usage: npx tsx _scripts/seed-intelligence-sample.ts

import { Pool } from 'pg'
import { config } from 'dotenv'
import { existsSync } from 'fs'
import path from 'path'

const envPath = path.resolve(process.cwd(), '.env.local')
if (existsSync(envPath)) config({ path: envPath })
else config()

async function getPool() {
  const connStr = process.env.DATABASE_URL || process.env.NEON_DATABASE_URL
  if (!connStr) throw new Error('DATABASE_URL not set')
  return new Pool({ connectionString: connStr, ssl: { rejectUnauthorized: false } })
}

async function main() {
  const pool = await getPool()
  console.log('Seeding sample intelligence data...\n')

  // Seed quarterly results
  const earnings = [
    { symbol: 'WABAG',   company_name: 'VA Tech Wabag',        fiscal_year: 2026, fiscal_quarter: 'Q2', result_date: '2025-11-10', revenue: 850,  ebitda: 120, pat: 78, eps: 12.5, revenue_yoy_growth: 28, revenue_qoq_growth: 11, pat_yoy_growth: 42,  pat_qoq_growth: 15,  ebitda_margin: 14.1, pat_margin: 9.2  },
    { symbol: 'KAYNES',  company_name: 'Kaynes Technology',     fiscal_year: 2026, fiscal_quarter: 'Q2', result_date: '2025-11-08', revenue: 780,  ebitda: 135, pat: 95, eps: 15.2, revenue_yoy_growth: 36, revenue_qoq_growth: 13, pat_yoy_growth: 48,  pat_qoq_growth: 17,  ebitda_margin: 17.3, pat_margin: 12.1 },
    { symbol: 'NETWEB',  company_name: 'Netweb Technologies',   fiscal_year: 2026, fiscal_quarter: 'Q2', result_date: '2025-11-05', revenue: 310,  ebitda: 58,  pat: 38, eps: 6.9,  revenue_yoy_growth: 44, revenue_qoq_growth: 9,  pat_yoy_growth: 40,  pat_qoq_growth: 8,   ebitda_margin: 18.7, pat_margin: 12.3 },
    { symbol: 'MTARTECH',company_name: 'MTAR Technologies',     fiscal_year: 2026, fiscal_quarter: 'Q2', result_date: '2025-11-12', revenue: 170,  ebitda: 32,  pat: 18, eps: 5.8,  revenue_yoy_growth: 8,  revenue_qoq_growth: -4, pat_yoy_growth: -6,  pat_qoq_growth: -10, ebitda_margin: 18.8, pat_margin: 10.5 },
    { symbol: 'DATAPATTNS',company_name: 'Data Patterns India', fiscal_year: 2026, fiscal_quarter: 'Q2', result_date: '2025-11-14', revenue: 410,  ebitda: 110, pat: 85, eps: 22.1, revenue_yoy_growth: 52, revenue_qoq_growth: 18, pat_yoy_growth: 58,  pat_qoq_growth: 22,  ebitda_margin: 26.8, pat_margin: 20.7 },
  ]

  for (const r of earnings) {
    await pool.query(`
      INSERT INTO quarterly_results (
        symbol, company_name, fiscal_year, fiscal_quarter, result_date,
        revenue, ebitda, pat, eps, revenue_yoy_growth, revenue_qoq_growth,
        pat_yoy_growth, pat_qoq_growth, ebitda_margin, pat_margin, updated_at
      ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,now())
      ON CONFLICT (symbol, fiscal_year, fiscal_quarter) DO UPDATE SET
        revenue=EXCLUDED.revenue, pat=EXCLUDED.pat,
        revenue_yoy_growth=EXCLUDED.revenue_yoy_growth,
        pat_yoy_growth=EXCLUDED.pat_yoy_growth, updated_at=now()
    `, [r.symbol, r.company_name, r.fiscal_year, r.fiscal_quarter, r.result_date,
        r.revenue, r.ebitda, r.pat, r.eps, r.revenue_yoy_growth, r.revenue_qoq_growth,
        r.pat_yoy_growth, r.pat_qoq_growth, r.ebitda_margin, r.pat_margin])
    console.log(`  ✓ ${r.symbol} quarterly results`)
  }

  // Seed management commentary
  const commentary = [
    { symbol: 'WABAG',    company_name: 'VA Tech Wabag',      quarter: 'Q2FY26', order_book_cr: 14000, order_book_coverage: 'Strong multi-year coverage', management_tone: 'strong positive improving', guidance_direction: 'positive maintain', key_growth_drivers: ['municipal water','industrial orders','international projects'], key_risks: ['execution delays'], positive_surprises: ['order book visibility'], negative_surprises: [], mgmt_quality_score: 8, confidence: 'High' },
    { symbol: 'KAYNES',   company_name: 'Kaynes Technology',  quarter: 'Q2FY26', order_book_cr: 5000,  order_book_coverage: 'Healthy order book',         management_tone: 'robust strong positive',   guidance_direction: 'positive raise',    key_growth_drivers: ['EMS demand','semiconductor','exports'],              key_risks: ['working capital'],                    positive_surprises: ['margin expansion'],    negative_surprises: [], mgmt_quality_score: 8, confidence: 'High'   },
    { symbol: 'NETWEB',   company_name: 'Netweb Technologies',quarter: 'Q2FY26', order_book_cr: 2200,  order_book_coverage: 'Solid pipeline',             management_tone: 'positive improving',       guidance_direction: 'positive maintain', key_growth_drivers: ['AI servers','HPC demand','govt orders'],             key_risks: ['supply chain'],                       positive_surprises: ['revenue beat'],       negative_surprises: [], mgmt_quality_score: 7, confidence: 'High'   },
    { symbol: 'MTARTECH', company_name: 'MTAR Technologies',  quarter: 'Q2FY26', order_book_cr: 900,   order_book_coverage: 'Moderate coverage',          management_tone: 'cautious muted pressure',  guidance_direction: 'stable cautious',   key_growth_drivers: ['clean energy recovery'],                            key_risks: ['client concentration','execution delay'], positive_surprises: [],                 negative_surprises: ['margin pressure'], mgmt_quality_score: 5, confidence: 'Medium' },
  ]

  for (const r of commentary) {
    await pool.query(`
      INSERT INTO management_commentary (
        nse_symbol, company_name, quarter, order_book_cr, order_book_coverage,
        management_tone, guidance_direction, key_growth_drivers, key_risks,
        positive_surprises, negative_surprises, mgmt_quality_score,
        data_source, confidence, extraction_notes, updated_at
      ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9::jsonb,$10::jsonb,$11::jsonb,$12,'sample_seed',$13,'Seed data',now())
      ON CONFLICT DO NOTHING
    `, [r.symbol, r.company_name, r.quarter, r.order_book_cr, r.order_book_coverage,
        r.management_tone, r.guidance_direction,
        JSON.stringify(r.key_growth_drivers), JSON.stringify(r.key_risks),
        JSON.stringify(r.positive_surprises), JSON.stringify(r.negative_surprises),
        r.mgmt_quality_score, r.confidence])
    console.log(`  ✓ ${r.symbol} commentary`)
  }

  // Seed AMFI flows
  const amfiFlows = [
    { report_month: 5, report_year: 2026, category: 'equity',  sub_category: 'flexicap',       net_inflow: 21800, aum: 520000, mom_change: 5.2,  yoy_change: 31 },
    { report_month: 5, report_year: 2026, category: 'equity',  sub_category: 'smallcap',       net_inflow: 4200,  aum: 340000, mom_change: 3.1,  yoy_change: 28 },
    { report_month: 5, report_year: 2026, category: 'equity',  sub_category: 'midcap',         net_inflow: 5100,  aum: 310000, mom_change: 4.8,  yoy_change: 32 },
    { report_month: 5, report_year: 2026, category: 'debt',    sub_category: 'short duration', net_inflow: -2500, aum: 190000, mom_change: -1.2, yoy_change: 5  },
    { report_month: 5, report_year: 2026, category: 'liquid',  sub_category: 'liquid',         net_inflow: 1800,  aum: 130000, mom_change: 0.8,  yoy_change: 8  },
  ]

  for (const r of amfiFlows) {
    await pool.query(`
      INSERT INTO amfi_category_flows (report_month, report_year, category, sub_category, net_inflow, aum, mom_change, yoy_change)
      VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
      ON CONFLICT (report_month, report_year, category, sub_category) DO UPDATE SET
        net_inflow=EXCLUDED.net_inflow, aum=EXCLUDED.aum, updated_at=now()
    `, [r.report_month, r.report_year, r.category, r.sub_category, r.net_inflow, r.aum, r.mom_change, r.yoy_change])
  }
  console.log('  ✓ AMFI flows (May 2026)')

  console.log('\n✅ Seed complete. Now run:')
  console.log('   npx tsx _scripts/run-intelligence-scoring.ts')

  await pool.end()
}

main().catch(e => { console.error(e); process.exit(1) })
