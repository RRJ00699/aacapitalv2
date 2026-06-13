import { fail, ok, sql } from '@/lib/db';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const [topEarnings, topCommentary, amfi, warningEarnings, cautiousCommentary] = await Promise.all([
      sql`SELECT * FROM latest_earnings_acceleration ORDER BY total_score DESC NULLS LAST LIMIT 10`,
      sql`SELECT * FROM latest_management_commentary_score ORDER BY total_score DESC NULLS LAST LIMIT 10`,
      sql`SELECT * FROM latest_amfi_liquidity_score LIMIT 1`,
      sql`SELECT * FROM latest_earnings_acceleration WHERE acceleration_status IN ('WARNING','DECELERATING') ORDER BY total_score ASC NULLS LAST LIMIT 10`,
      sql`SELECT * FROM latest_management_commentary_score WHERE commentary_status IN ('CAUTIOUS','DETERIORATING') ORDER BY total_score ASC NULLS LAST LIMIT 10`,
    ]);

    return ok({
      top_earnings: topEarnings,
      top_commentary: topCommentary,
      amfi_liquidity: amfi[0] || null,
      warning_earnings: warningEarnings,
      cautious_commentary: cautiousCommentary,
    });
  } catch (error) {
    return fail('Failed to load intelligence dashboard.', 500, String(error));
  }
}
