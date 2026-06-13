// app/api/ipo-dna/route.ts
// IPO DNA Engine — powered by real historical data
// GET /api/ipo-dna?name=NSDL          → find similar historical IPOs
// GET /api/ipo-dna?view=patterns      → sector/regime win rate patterns
// GET /api/ipo-dna?view=anchor-stats  → anchor investor win rates
// POST /api/ipo-dna                   → score a new IPO against history

import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

function db() { return neon(process.env.DATABASE_URL!) }

// ── Similarity scoring between two IPOs ──────────────────────────────────────
function similarityScore(
  target: Record<string, number | string | null>,
  historical: Record<string, number | string | null>
): number {
  let score = 0
  let maxScore = 0

  // QIB subscription (weight 25) — corr 0.733
  if (target.qib_x && historical.qib_x) {
    maxScore += 25
    const diff = Math.abs(Number(target.qib_x) - Number(historical.qib_x))
    const pct = diff / Math.max(Number(target.qib_x), Number(historical.qib_x))
    score += 25 * Math.max(0, 1 - pct)
  }

  // NII subscription (weight 30) — corr 0.758, strongest predictor
  if (target.nii_x && historical.nii_x) {
    maxScore += 30
    const diff = Math.abs(Number(target.nii_x) - Number(historical.nii_x))
    const pct = diff / Math.max(Number(target.nii_x), Number(historical.nii_x))
    score += 30 * Math.max(0, 1 - pct)
  }

  // GMP (weight 15)
  if (target.gmp_pct_of_issue && historical.gmp_pct_of_issue) {
    maxScore += 15
    const diff = Math.abs(Number(target.gmp_pct_of_issue) - Number(historical.gmp_pct_of_issue))
    score += 15 * Math.max(0, 1 - diff / 100)
  }

  // Anchor score (weight 15)
  if (target.anchor_score && historical.anchor_score) {
    maxScore += 15
    const diff = Math.abs(Number(target.anchor_score) - Number(historical.anchor_score))
    score += 15 * Math.max(0, 1 - diff / 100)
  }

  // Market regime match (weight 10)
  if (target.market_regime && historical.market_regime) {
    maxScore += 10
    if (target.market_regime === historical.market_regime) score += 10
    else if (
      (target.market_regime === "hot" && historical.market_regime === "normal") ||
      (target.market_regime === "normal" && historical.market_regime === "hot")
    ) score += 5
  }

  // Sector match (weight 5)
  if (target.sector && historical.sector) {
    maxScore += 5
    const tSector = String(target.sector).toLowerCase()
    const hSector = String(historical.sector).toLowerCase()
    if (tSector === hSector) score += 5
    else if (tSector.split("/")[0] === hSector.split("/")[0]) score += 3
  }

  return maxScore > 0 ? Math.round(score / maxScore * 100) : 0
}

export async function GET(req: NextRequest) {
  const sql = db()
  const name = req.nextUrl.searchParams.get("name")
  const view = req.nextUrl.searchParams.get("view")

  try {
    // ── View: Historical patterns ──────────────────────────────────────────────
    if (view === "patterns") {
      const sectorWins = await sql`
        SELECT
          sector,
          COUNT(*) as total_ipos,
          ROUND(AVG(listing_gain_pct)::numeric, 1) as avg_listing_gain,
          COUNT(CASE WHEN listing_gain_pct > 20 THEN 1 END) as wins_20pct,
          COUNT(CASE WHEN listing_gain_pct > 50 THEN 1 END) as wins_50pct,
          ROUND(COUNT(CASE WHEN listing_gain_pct > 20 THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0), 1) as win_rate_pct,
          ROUND(AVG(nii_x)::numeric, 1) as avg_nii,
          ROUND(AVG(qib_x)::numeric, 1) as avg_qib
        FROM ipo_history
        WHERE listing_gain_pct IS NOT NULL AND sector IS NOT NULL
          AND sector != 'Unknown'
        GROUP BY sector
        HAVING COUNT(*) >= 2
        ORDER BY avg_listing_gain DESC
        LIMIT 25
      `

      const regimeStats = await sql`
        SELECT
          market_regime,
          COUNT(*) as total_ipos,
          ROUND(AVG(listing_gain_pct)::numeric, 1) as avg_gain,
          COUNT(CASE WHEN listing_gain_pct > 20 THEN 1 END) as wins,
          ROUND(COUNT(CASE WHEN listing_gain_pct > 20 THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0), 1) as win_rate
        FROM ipo_history
        WHERE listing_gain_pct IS NOT NULL AND market_regime IS NOT NULL
        GROUP BY market_regime
        ORDER BY avg_gain DESC
      `

      const subscriptionBuckets = await sql`
        SELECT
          CASE
            WHEN nii_x > 300 THEN 'Elite (NII>300x)'
            WHEN nii_x > 100 THEN 'Strong (NII 100-300x)'
            WHEN nii_x > 30  THEN 'Moderate (NII 30-100x)'
            WHEN nii_x > 0   THEN 'Weak (NII<30x)'
            ELSE 'Unknown'
          END as nii_bucket,
          COUNT(*) as ipos,
          ROUND(AVG(listing_gain_pct)::numeric, 1) as avg_gain,
          ROUND(COUNT(CASE WHEN listing_gain_pct > 20 THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0), 1) as win_rate
        FROM ipo_history
        WHERE listing_gain_pct IS NOT NULL
        GROUP BY nii_bucket
        ORDER BY avg_gain DESC
      `

      return NextResponse.json({
        ok: true,
        sector_patterns: sectorWins,
        regime_stats: regimeStats,
        subscription_buckets: subscriptionBuckets,
      })
    }

    // ── View: Anchor stats ─────────────────────────────────────────────────────
    if (view === "anchor-stats") {
      const anchorWinRates = await sql`
        SELECT
          h.anchor_quality_score,
          COUNT(*) as ipos,
          ROUND(AVG(i.listing_gain_pct)::numeric, 1) as avg_gain,
          ROUND(COUNT(CASE WHEN i.listing_gain_pct > 20 THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0), 1) as win_rate,
          ROUND(AVG(CASE WHEN h.sovereign_present THEN i.listing_gain_pct END)::numeric, 1) as sovereign_avg_gain,
          ROUND(AVG(CASE WHEN h.tier1_mf_present THEN i.listing_gain_pct END)::numeric, 1) as tier1mf_avg_gain
        FROM ipo_anchor_history h
        JOIN ipo_history i ON LOWER(h.ipo_name) = LOWER(i.name)
        WHERE i.listing_gain_pct IS NOT NULL
        GROUP BY h.anchor_quality_score
        ORDER BY h.anchor_quality_score DESC
      `

      const investors = await sql`
        SELECT rank, investor_name, category, quality_score, classification
        FROM anchor_investor_master
        ORDER BY rank
      `

      return NextResponse.json({
        ok: true,
        anchor_win_rates: anchorWinRates,
        investor_rankings: investors,
      })
    }

    // ── DNA similarity: find historical comps for a named IPO ─────────────────
    if (name) {
      // Get the target IPO (could be in ipo_master or ipo_history)
      const target = await sql`
        SELECT name, sector, qib_x, nii_x, retail_x, gmp_pct_of_issue,
               anchor_score, market_regime, listing_gain_pct, ipo_score
        FROM ipo_history
        WHERE name ILIKE ${'%' + name + '%'}
        LIMIT 1
      `

      // Also check live ipo_master
      const liveMaster = await sql`
        SELECT name, conviction_score as ipo_score
        FROM ipo_master
        WHERE name ILIKE ${'%' + name + '%'}
        LIMIT 1
      `.catch(() => [])

      // Get all historical IPOs with subscription data for comparison
      const historicals = await sql`
        SELECT name, year, sector, qib_x, nii_x, retail_x, total_x,
               gmp_pct_of_issue, anchor_score, market_regime,
               listing_gain_pct, d1_close_gain_pct, ipo_score,
               listing_gain_bucket, subscription_tier, dna_similarity_tags
        FROM ipo_history
        WHERE sub_data = true AND listing_gain_pct IS NOT NULL
          AND name NOT ILIKE ${'%' + name + '%'}
        ORDER BY year DESC
      `

      if (!target.length && !historicals.length) {
        return NextResponse.json({ ok: false, error: "IPO not found in history" }, { status: 404 })
      }

      const targetData = target[0] ?? liveMaster[0] ?? {}

      // Score similarity against all historical IPOs
      type ScoredIPO = Record<string, unknown> & { similarity_score: number }
      const scored = (historicals.map(h => ({
        ...h,
        similarity_score: similarityScore(
          targetData as Record<string, number | string | null>,
          h as Record<string, number | string | null>
        ),
      })) as ScoredIPO[])
      .filter(h => h.similarity_score >= 30)
      .sort((a, b) => b.similarity_score - a.similarity_score)
      .slice(0, 10)

      // Compute expected returns from similar IPOs
      const avgListing = scored.length
        ? Math.round(scored.reduce((s, h) => s + (Number(h.listing_gain_pct) || 0), 0) / scored.length * 10) / 10
        : null
      const wins = scored.filter(h => Number(h.listing_gain_pct) > 20).length
      const winRate = scored.length ? Math.round(wins / scored.length * 100) : null

      return NextResponse.json({
        ok: true,
        target: targetData,
        similar_ipos: scored,
        prediction: {
          expected_listing_gain: avgListing,
          win_rate_pct: winRate,
          sample_size: scored.length,
          confidence: scored.length >= 5 ? "high" : scored.length >= 3 ? "medium" : "low",
          bull_case: scored.length
            ? Math.round(Math.max(...scored.map(h => Number(h.listing_gain_pct) || 0)) * 10) / 10
            : null,
          bear_case: scored.length
            ? Math.round(Math.min(...scored.map(h => Number(h.listing_gain_pct) || 0)) * 10) / 10
            : null,
        }
      })
    }

    // ── Default: summary stats ─────────────────────────────────────────────────
    const summary = await sql`
      SELECT
        COUNT(*) as total_ipos,
        COUNT(CASE WHEN sub_data THEN 1 END) as with_subscription,
        COUNT(CASE WHEN listing_gain_pct IS NOT NULL THEN 1 END) as with_listing,
        ROUND(AVG(listing_gain_pct)::numeric, 1) as overall_avg_gain,
        COUNT(CASE WHEN listing_gain_pct > 20 THEN 1 END) as wins_20pct,
        MIN(year) as earliest_year, MAX(year) as latest_year
      FROM ipo_history
    `

    return NextResponse.json({ ok: true, summary: summary[0] })

  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "Unknown error"
    // Table may not exist yet
    if (msg.includes("does not exist")) {
      return NextResponse.json({
        ok: false,
        error: "IPO history not imported yet. Run: node scripts/ipo-history-import.mjs",
      }, { status: 503 })
    }
    return NextResponse.json({ ok: false, error: msg }, { status: 500 })
  }
}

// ── POST: Score a new IPO against all history ─────────────────────────────────
export async function POST(req: NextRequest) {
  try {
    const sql = db()
    const body = await req.json()
    const { name, sector, qib_x, nii_x, retail_x, gmp_pct, anchor_score, regime } = body

    if (!name) return NextResponse.json({ ok: false, error: "name required" }, { status: 400 })

    const target = { name, sector, qib_x, nii_x, retail_x, gmp_pct_of_issue: gmp_pct, anchor_score, market_regime: regime }

    // Get all scored historical IPOs
    const historicals = await sql`
      SELECT name, year, sector, qib_x, nii_x, retail_x, gmp_pct_of_issue,
             anchor_score, market_regime, listing_gain_pct, listing_gain_bucket,
             subscription_tier, dna_similarity_tags, ipo_score
      FROM ipo_history
      WHERE sub_data = true AND listing_gain_pct IS NOT NULL
    `

    type ScoredIPO2 = Record<string, unknown> & { similarity: number }
    const scored = (historicals.map(h => ({
      ...h,
      similarity: similarityScore(
        target as unknown as Record<string, number | string | null>,
        h as Record<string, number | string | null>
      ),
    })) as ScoredIPO2[])
    .filter(h => h.similarity >= 25)
    .sort((a, b) => b.similarity - a.similarity)
    .slice(0, 10)

    // Expected returns
    const avgGain = scored.length
      ? Math.round(scored.reduce((s, h) => s + (Number(h.listing_gain_pct) || 0), 0) / scored.length * 10) / 10
      : null
    const winRate = scored.length
      ? Math.round(scored.filter(h => Number(h.listing_gain_pct) > 20).length / scored.length * 100)
      : null

    // Tags from similar IPOs — what patterns do they share?
    const allTags = scored.flatMap(h => (h.dna_similarity_tags as string[]) ?? [])
    const tagFreq: Record<string, number> = {}
    for (const t of allTags) tagFreq[t] = (tagFreq[t] ?? 0) + 1
    const dominantTags = Object.entries(tagFreq)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([tag]) => tag)

    // Regime adjustment
    const regimeMultiplier = regime === "hot" ? 1.2 : regime === "cold" ? 0.7 : 1.0
    const regimeAdjustedGain = avgGain !== null ? Math.round(avgGain * regimeMultiplier * 10) / 10 : null

    return NextResponse.json({
      ok: true,
      input: target,
      similar_ipos: scored.slice(0, 5),
      dna_prediction: {
        expected_listing_gain: avgGain,
        regime_adjusted_gain: regimeAdjustedGain,
        win_rate_pct: winRate,
        confidence: scored.length >= 5 ? "high" : scored.length >= 3 ? "medium" : "low",
        sample_size: scored.length,
        bull_case: scored.length ? Math.round(Math.max(...scored.map(h => Number(h.listing_gain_pct) || 0)) * 10) / 10 : null,
        bear_case: scored.length ? Math.round(Math.min(...scored.map(h => Number(h.listing_gain_pct) || 0)) * 10) / 10 : null,
        dominant_patterns: dominantTags,
        regime_note: regime === "cold"
          ? "COLD market — reduce expected gain by 30%, apply only conviction ≥80"
          : regime === "hot"
          ? "HOT market — historical comps likely understate gain"
          : "NORMAL market — historical comps are reliable",
      }
    })

  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "Unknown error"
    return NextResponse.json({ ok: false, error: msg }, { status: 500 })
  }
}
