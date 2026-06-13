import { fail, normalizeSymbol, ok, sql } from '@/lib/db';

export const dynamic = 'force-dynamic';

export async function GET(req: Request) {
  try {
    const { searchParams } = new URL(req.url);
    const symbol = normalizeSymbol(searchParams.get('symbol'));
    const limit = Number(searchParams.get('limit') || 50);

    if (symbol) {
      const commentary = await sql`
        SELECT *
        FROM latest_management_commentary
        WHERE symbol = ${symbol}
        LIMIT 1
      `;
      const score = await sql`
        SELECT *
        FROM latest_management_commentary_score
        WHERE symbol = ${symbol}
        LIMIT 1
      `;
      return ok({ commentary: commentary[0] || null, score: score[0] || null });
    }

    const rows = await sql`
      SELECT s.*, c.management_tone, c.guidance_direction, c.order_book_cr, c.confidence
      FROM latest_management_commentary_score s
      LEFT JOIN latest_management_commentary c ON c.symbol = s.symbol
      ORDER BY s.total_score DESC NULLS LAST
      LIMIT ${Math.min(Math.max(limit, 1), 200)}
    `;
    return ok(rows);
  } catch (error) {
    return fail('Failed to load management commentary intelligence.', 500, String(error));
  }
}
