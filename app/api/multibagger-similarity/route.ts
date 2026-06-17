// app/api/multibagger-similarity/route.ts
// Returns historical multibagger analogs for a symbol or top matches across the universe.

import { NextRequest, NextResponse } from 'next/server';
import { sql } from '@/lib/db';
import { probabilityFromSimilarity } from '@/lib/intelligence/historical-similarity';

function normalizeSymbol(value: string | null): string | null {
  const s = String(value || '').trim().toUpperCase();
  return s || null;
}

export async function GET(req: NextRequest) {
  const symbol = normalizeSymbol(req.nextUrl.searchParams.get('symbol'));
  const limit = Math.min(50, Math.max(1, Number(req.nextUrl.searchParams.get('limit') || 5)));

  try {
    const rows = symbol
      ? await sql`
          SELECT
            ms.symbol,
            ms.similar_to,
            COALESCE(sf.name, ms.similar_to) AS similar_to_name,
            sf.industry AS similar_to_industry,
            ms.historical_event_id,
            ms.historical_start_date,
            ms.historical_end_date,
            ms.historical_return_pct,
            ms.historical_tier,
            ms.similarity_score,
            ms.dtw_distance,
            ms.p_2x,
            ms.p_5x,
            ms.p_10x,
            ms.notes,
            ms.updated_at
          FROM multibagger_similarity ms
          LEFT JOIN stock_fundamentals sf ON sf.nse_symbol = ms.similar_to
          WHERE ms.symbol = ${symbol}
            AND ms.status = 'ACTIVE'
          ORDER BY ms.similarity_score DESC, ms.historical_return_pct DESC NULLS LAST
          LIMIT ${limit}
        `
      : await sql`
          SELECT
            ms.symbol,
            COALESCE(f.name, ms.symbol) AS name,
            f.industry,
            f.market_cap,
            MAX(ms.similarity_score) AS best_similarity,
            MAX(ms.p_2x) AS p_2x,
            MAX(ms.p_5x) AS p_5x,
            MAX(ms.p_10x) AS p_10x,
            COUNT(*) AS match_count,
            MAX(ms.updated_at) AS updated_at
          FROM multibagger_similarity ms
          LEFT JOIN stock_fundamentals f ON f.nse_symbol = ms.symbol
          WHERE ms.status = 'ACTIVE'
          GROUP BY ms.symbol, f.name, f.industry, f.market_cap
          ORDER BY best_similarity DESC, p_5x DESC NULLS LAST
          LIMIT ${limit}
        `;

    const data = rows.map((r: any) => {
      const similarity = Number(r.similarity_score ?? r.best_similarity ?? 0);
      const fallback = probabilityFromSimilarity(similarity, Number(r.historical_return_pct || 0));
      return {
        ...r,
        similarity_score: similarity,
        best_similarity: r.best_similarity ? Number(r.best_similarity) : undefined,
        historical_return_pct: r.historical_return_pct ? Number(r.historical_return_pct) : undefined,
        p_2x: Number(r.p_2x ?? fallback.p2x),
        p_5x: Number(r.p_5x ?? fallback.p5x),
        p_10x: Number(r.p_10x ?? fallback.p10x),
      };
    });

    return NextResponse.json({ ok: true, count: data.length, symbol, data });
  } catch (err: any) {
    console.error('[multibagger-similarity]', err?.message || err);
    if (String(err?.message || '').includes('multibagger_similarity')) {
      return NextResponse.json({
        ok: false,
        error: 'Historical similarity table missing. Run: npx tsx _scripts/engines/multibagger_similarity_engine.ts --limit 500 --top 5',
      }, { status: 503 });
    }
    return NextResponse.json({ ok: false, error: err?.message || 'Unknown error' }, { status: 500 });
  }
}
