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

    const intel = await pool.query(`
      SELECT * FROM transcript_intelligence
      WHERE nse_symbol = $1
      ORDER BY quarter DESC
      LIMIT 8
    `, [symbol]);

    const docs = await pool.query(`
      SELECT id, nse_symbol, quarter, document_type, source_url, created_at
      FROM transcript_documents
      WHERE nse_symbol = $1
      ORDER BY created_at DESC
      LIMIT 10
    `, [symbol]);

    return NextResponse.json({
      symbol,
      latest: intel.rows[0] || null,
      history: intel.rows,
      documents: docs.rows,
    });
  } catch (error: any) {
    console.error('/api/transcript-intel error', error);
    return NextResponse.json({ error: error.message || 'Internal error' }, { status: 500 });
  }
}
