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

    const quality = await pool.query(`
      SELECT * FROM management_quality_history
      WHERE nse_symbol = $1
      ORDER BY quarter DESC
      LIMIT 8
    `, [symbol]);

    const legacy = await pool.query(`
      SELECT * FROM management_commentary
      WHERE nse_symbol = $1
      ORDER BY quarter DESC
      LIMIT 4
    `, [symbol]);

    return NextResponse.json({
      symbol,
      latest: quality.rows[0] || null,
      history: quality.rows,
      legacyCommentary: legacy.rows,
    });
  } catch (error: any) {
    console.error('/api/management-v2 error', error);
    return NextResponse.json({ error: error.message || 'Internal error' }, { status: 500 });
  }
}
