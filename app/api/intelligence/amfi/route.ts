import { fail, ok, sql } from '@/lib/db';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const latest = await sql`SELECT * FROM latest_amfi_liquidity_score LIMIT 1`;
    const score = latest[0] || null;

    const flows = score
      ? await sql`
          SELECT *
          FROM amfi_category_flows
          WHERE report_year = ${score.report_year}
            AND report_month = ${score.report_month}
          ORDER BY net_inflow DESC NULLS LAST
        `
      : [];

    return ok({ score, flows });
  } catch (error) {
    return fail('Failed to load AMFI liquidity intelligence.', 500, String(error));
  }
}
