import { NextRequest, NextResponse } from 'next/server';
import { Pool } from 'pg';

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: process.env.DATABASE_URL?.includes('neon.tech') ? { rejectUnauthorized: false } : undefined,
});

export const dynamic = 'force-dynamic';

export async function GET(req: NextRequest) {
  try {
    const symbol = req.nextUrl.searchParams.get('symbol')?.trim().toUpperCase();
    if (!symbol) return NextResponse.json({ error: 'symbol is required' }, { status: 400 });

    const summary = await pool.query(`
      SELECT * FROM mf_stock_summary
      WHERE nse_symbol = $1
      ORDER BY month DESC
      LIMIT 12
    `, [symbol]);

    const latestMonth = summary.rows[0]?.month;
    const topFunds = latestMonth ? await pool.query(`
      SELECT amc_name, scheme_name, market_value_cr, portfolio_weight_pct
      FROM mf_scheme_holdings
      WHERE nse_symbol = $1 AND month = $2
      ORDER BY market_value_cr DESC NULLS LAST
      LIMIT 20
    `, [symbol, latestMonth]) : { rows: [] };

    return NextResponse.json({
      symbol,
      latest: summary.rows[0] || null,
      trend: summary.rows,
      topFunds: topFunds.rows,
    });
  } catch (error: any) {
    console.error('/api/mf-intelligence error', error);
    return NextResponse.json({ error: error.message || 'Internal error' }, { status: 500 });
  }
}
