import { NextRequest, NextResponse } from 'next/server';
import { Pool } from 'pg';

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: process.env.DATABASE_URL?.includes('neon.tech') ? { rejectUnauthorized: false } : undefined,
});

export const dynamic = 'force-dynamic';

const n = (v: any, fallback = 50) => {
  const x = Number(v);
  return Number.isFinite(x) ? x : fallback;
};
const clamp = (x: number) => Math.max(0, Math.min(100, Math.round(x)));

function technicalScore(return3m: any, return6m: any) {
  const r3 = Number(return3m || 0);
  const r6 = Number(return6m || 0);
  let score = 50;
  if (r3 >= 30) score += 25;
  else if (r3 >= 15) score += 18;
  else if (r3 >= 5) score += 10;
  else if (r3 < -10) score -= 15;
  if (r6 >= 50) score += 20;
  else if (r6 >= 25) score += 12;
  else if (r6 < -20) score -= 15;
  return clamp(score);
}

export async function GET(req: NextRequest) {
  try {
    const symbol = req.nextUrl.searchParams.get('symbol')?.trim().toUpperCase();
    if (!symbol) return NextResponse.json({ error: 'symbol is required' }, { status: 400 });

    const fRes = await pool.query(`SELECT * FROM stock_fundamentals WHERE nse_symbol = $1`, [symbol]);
    if (fRes.rowCount === 0) return NextResponse.json({ error: 'Symbol not found' }, { status: 404 });
    const f = fRes.rows[0];

    const obRes = await pool.query(`SELECT * FROM order_book_signals WHERE nse_symbol = $1`, [symbol]);
    const transcriptRes = await pool.query(`SELECT * FROM transcript_intelligence WHERE nse_symbol = $1 ORDER BY quarter DESC LIMIT 1`, [symbol]);
    const mgmtRes = await pool.query(`SELECT * FROM management_quality_history WHERE nse_symbol = $1 ORDER BY quarter DESC LIMIT 1`, [symbol]);
    const ownerRes = await pool.query(`SELECT * FROM ownership_signals WHERE nse_symbol = $1`, [symbol]);
    const mfRes = await pool.query(`SELECT * FROM mf_stock_summary WHERE nse_symbol = $1 ORDER BY month DESC LIMIT 1`, [symbol]);

    const business = n(f.business_dna_score);
    const earnings = n(f.earnings_score);
    const smartMoney = n(f.smart_money_score);
    const sector = n(f.sector_rotation_score);
    const technical = technicalScore(f.return_3m, f.return_6m);
    const orderBook = n(obRes.rows[0]?.ob_score);
    const transcript = n(transcriptRes.rows[0]?.transcript_score);
    const management = n(mgmtRes.rows[0]?.score ?? mgmtRes.rows[0]?.credibility_score);
    const ownership = n(ownerRes.rows[0]?.ownership_score);
    const mf = n(mfRes.rows[0]?.accumulation_score);

    const finalScore = clamp(
      business * 0.20 +
      earnings * 0.15 +
      smartMoney * 0.10 +
      sector * 0.10 +
      technical * 0.10 +
      orderBook * 0.10 +
      transcript * 0.10 +
      management * 0.05 +
      ownership * 0.05 +
      mf * 0.05
    );

    let conviction = 'WATCH';
    if (finalScore >= 80) conviction = 'HIGH';
    else if (finalScore >= 70) conviction = 'GOOD';
    else if (finalScore >= 60) conviction = 'NEUTRAL';
    else if (finalScore < 50) conviction = 'AVOID';

    return NextResponse.json({
      symbol,
      name: f.name,
      industry: f.industry,
      market_cap: f.market_cap,
      final_score: finalScore,
      conviction,
      engines: {
        business_dna: business,
        earnings,
        smart_money: smartMoney,
        sector_rotation: sector,
        technical,
        order_book: orderBook,
        transcript_intelligence: transcript,
        management_quality: management,
        ownership_tracker: ownership,
        mf_intelligence: mf,
      },
      signals: {
        ownership: ownerRes.rows[0]?.signal || null,
        mf: mfRes.rows[0]?.signal || null,
        order_book: obRes.rows[0]?.trend || null,
      },
    });
  } catch (error: any) {
    console.error('/api/convergence-v4 error', error);
    return NextResponse.json({ error: error.message || 'Internal error' }, { status: 500 });
  }
}
