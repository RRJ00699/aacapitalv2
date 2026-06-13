import { fail, normalizeSymbol, ok, sql } from '@/lib/db';

export const dynamic = 'force-dynamic';

export async function GET(req: Request) {
  try {
    const { searchParams } = new URL(req.url);
    const symbol = normalizeSymbol(searchParams.get('symbol'));
    const limit = Number(searchParams.get('limit') || 50);

    if (symbol) {
      const rows = await sql`
        SELECT *
        FROM latest_earnings_acceleration
        WHERE symbol = ${symbol}
        LIMIT 1
      `;
      return ok(rows[0] || null);
    }

    const rows = await sql`
      SELECT *
      FROM latest_earnings_acceleration
      ORDER BY total_score DESC NULLS LAST
      LIMIT ${Math.min(Math.max(limit, 1), 200)}
    `;
    return ok(rows);
  } catch (error) {
    return fail('Failed to load earnings intelligence.', 500, String(error));
  }
}
